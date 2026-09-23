"""Deterministic outlier detection and lost-demand estimation."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from .models import WorkflowState
from .primitives import _percentile, _zero_metrics, _date_range, _clamp


def detect_outliers(state: WorkflowState) -> str:
    state.outlier_dates = {}
    # Inspect per-client/day totals before daily aggregation hides a one-off
    # order among normal sales. Client IDs stay inside this deterministic step.
    grouped = defaultdict(lambda: defaultdict(float))
    for row in state.raw["sales"]:
        if row.get("customer_id"):
            key = (date.fromisoformat(row["date"]), row["customer_id"])
            grouped[row["sku"]][key] += float(row["units"])
    count = 0
    for sku, daily in state.daily_sales.items():
        cleaned = dict(daily)
        removed = defaultdict(float)
        client_days = set()
        transactions = grouped[sku]
        if len(transactions) >= 8:
            amounts = sorted(transactions.values())
            q1, q3 = _percentile(amounts, 0.25), _percentile(amounts, 0.75)
            limit = max(q3 + 3 * (q3 - q1), _percentile(amounts, 0.5) * 5)
            candidates = [
                (day, client) for (day, client), amount in transactions.items() if amount > limit
            ]
            candidate_counts = Counter(client for _, client in candidates)
            for day, client in candidates:
                if candidate_counts[client] == 1:
                    quantity = transactions[(day, client)]
                    cleaned[day] = max(0, cleaned[day] - quantity)
                    removed[day] += quantity
                    client_days.add(day)
        state.regular_daily_sales[sku] = cleaned
        state.client_outlier_dates[sku] = client_days
        values = sorted(cleaned.values())
        if len(values) < 4:
            state.outlier_dates[sku] = set()
            state.removed_by_day[sku] = dict(removed)
            count += len(client_days)
            continue
        q1 = _percentile(values, 0.25)
        q3 = _percentile(values, 0.75)
        iqr = q3 - q1
        threshold = q3 + 1.5 * iqr if iqr > 0 else q3 * 3
        flagged = {day for day, units in cleaned.items() if q3 > 0 and units > threshold}
        state.outlier_dates[sku] = flagged
        for day in flagged:
            removed[day] += cleaned[day]
        state.removed_by_day[sku] = dict(removed)
        count += len(flagged | client_days)
    state.anomaly_count = count
    return f"Marked {count} daily sales observations as outliers"


def estimate_lost_demand(state: WorkflowState) -> str:
    compensated = 0
    for sku, product in state.products.items():
        if not product["active"]:
            continue
        daily = state.regular_daily_sales.get(sku, state.daily_sales.get(sku, {}))
        if not daily:
            state.metrics[sku] = _zero_metrics()
            continue
        observed = set(daily) | state.stockout_dates.get(sku, set())
        last_day = max(observed)
        first_day = max(min(observed), last_day - timedelta(days=27))
        calendar_days = (last_day - first_day).days + 1
        window = _date_range(first_day, last_day)
        outliers = state.outlier_dates.get(sku, set())
        stockouts = state.stockout_dates.get(sku, set())
        valid_units = sum(
            daily.get(day, 0.0) for day in window if day not in outliers and day not in stockouts
        )
        baseline = valid_units / calendar_days
        stockout_days = sum(1 for day in window if day in stockouts)
        compensation = baseline * stockout_days
        if compensation > 0:
            compensated += 1

        seasonality = 1.0
        if calendar_days >= 28:
            recent = window[-7:]
            recent_mean = (
                sum(
                    daily.get(day, 0.0)
                    for day in recent
                    if day not in outliers and day not in stockouts
                )
                / 7
            )
            if baseline > 0:
                seasonality = _clamp(recent_mean / baseline, 0.75, 1.50)

        growth = 1.0
        if calendar_days >= 28:
            recent_14 = window[-14:]
            previous_14 = window[-28:-14]
            recent_valid = [
                day for day in recent_14 if day not in outliers and day not in stockouts
            ]
            previous_valid = [
                day for day in previous_14 if day not in outliers and day not in stockouts
            ]
            if len(recent_valid) >= 7 and len(previous_valid) >= 7:
                recent_mean = sum(daily.get(day, 0.0) for day in recent_valid) / 14
                previous_mean = sum(daily.get(day, 0.0) for day in previous_valid) / 14
                if previous_mean > 0:
                    growth = _clamp(recent_mean / previous_mean, 1.0, 1.30)

        outlier_units = sum(
            units for day, units in state.removed_by_day.get(sku, {}).items() if day in window
        )
        state.metrics[sku] = {
            "calendar_days": float(calendar_days),
            "avg_daily_demand": (valid_units + compensation) / calendar_days,
            "stockout_compensation": compensation,
            "seasonality_factor": seasonality,
            "growth_factor": growth,
            "outlier_units_removed": outlier_units,
            "baseline_daily_demand": baseline,
            "calculation_start_date": first_day,
            "calculation_end_date": last_day,
        }
    return f"Estimated lost demand for {compensated} products"
