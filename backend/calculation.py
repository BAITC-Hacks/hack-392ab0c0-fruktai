from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .schemas import Recommendation, Reason, RecalculateResponse, SupplierOrder


SAFETY_Z = 1.65
MIN_SEASONALITY = 0.5
MAX_SEASONALITY = 2.0
MIN_GROWTH = -0.20
MAX_GROWTH = 0.50


REQUIRED_SALES = {"date", "sku", "quantity"}
REQUIRED_INVENTORY = {"sku", "supplier", "on_hand", "in_transit", "lead_time_days"}


def _clean_sku(value: object) -> str:
    text = str(value).strip().upper()
    if not text or text == "NAN":
        raise ValueError("sku must not be empty")
    return text


def _number(value: object, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not np.isfinite(result) or result < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return result


def validate_and_normalize(sales: pd.DataFrame, inventory: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing_sales = REQUIRED_SALES - set(sales.columns)
    missing_inventory = REQUIRED_INVENTORY - set(inventory.columns)
    if missing_sales:
        raise ValueError(f"sales CSV missing required columns: {sorted(missing_sales)}")
    if missing_inventory:
        raise ValueError(f"inventory CSV missing required columns: {sorted(missing_inventory)}")

    sales = sales.copy()
    inventory = inventory.copy()
    sales["date"] = pd.to_datetime(sales["date"], errors="coerce", utc=True)
    if sales["date"].isna().any():
        raise ValueError("sales.date contains invalid dates")
    sales["date"] = sales["date"].dt.tz_convert(None).dt.normalize()
    sales["sku"] = sales["sku"].map(_clean_sku)
    sales["quantity"] = sales["quantity"].map(lambda x: _number(x, "quantity"))
    if "customer_id" not in sales:
        sales["customer_id"] = "unknown"
    sales["customer_id"] = sales["customer_id"].fillna("unknown").astype(str).str.strip()
    if "stockout" not in sales:
        sales["stockout"] = False
    sales["stockout"] = sales["stockout"].map(_as_bool)

    inventory["sku"] = inventory["sku"].map(_clean_sku)
    for field in ("on_hand", "in_transit", "lead_time_days"):
        inventory[field] = inventory[field].map(lambda x, f=field: _number(x, f))
    inventory["lead_time_days"] = inventory["lead_time_days"].round().astype(int)
    for optional in ("name", "category", "seasonality_factor", "growth_rate"):
        if optional not in inventory:
            inventory[optional] = np.nan
    inventory["supplier"] = inventory["supplier"].fillna("Unknown supplier").astype(str).str.strip()
    if inventory["sku"].duplicated().any():
        raise ValueError("inventory CSV must contain one row per sku")
    return sales.sort_values(["sku", "date"], kind="mergesort"), inventory


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "да"}


def _robust_filter(values: pd.Series) -> tuple[pd.Series, float, str]:
    """Return mask, excluded units, and method. Never mutates the source data."""
    if len(values) < 4:
        return pd.Series(True, index=values.index), 0.0, "insufficient_history_fallback"
    median = float(values.median())
    mad = float(np.median(np.abs(values - median)))
    if mad > 0:
        robust_z = 0.6745 * (values - median).abs() / mad
        mask = robust_z <= 3.5
        method = "MAD"
    else:
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = float(q3 - q1)
        if iqr <= 0:
            # With a flat regular series, a single spike has zero MAD and zero IQR.
            # Keep the regular level and mark only materially larger observations.
            reference = max(median, float(values.mean()), 1.0)
            mask = values <= reference * 3.0
            method = "flat-series-threshold"
            excluded = float(values[~mask].sum())
            return mask, excluded, method
        mask = values <= q3 + 1.5 * iqr
        method = "IQR"
    if not bool(mask.any()):
        mask[:] = True
    return mask, float(values[~mask].sum()), method


def _bounded(value: float, lower: float, upper: float) -> float:
    return float(np.clip(value if np.isfinite(value) else 1.0, lower, upper))


def _growth_rate(daily: pd.Series) -> float:
    if len(daily) < 14:
        return 0.0
    split = max(7, len(daily) // 3)
    old = float(daily.iloc[:split].mean())
    recent = float(daily.iloc[-split:].mean())
    if old <= 0:
        return 0.0
    return _bounded((recent / old) - 1.0, MIN_GROWTH, MAX_GROWTH)


def _seasonality(sales: pd.DataFrame, baseline: float, as_of: pd.Timestamp, provided: object) -> float:
    if pd.notna(provided):
        return _bounded(float(provided), MIN_SEASONALITY, MAX_SEASONALITY)
    if baseline <= 0 or len(sales) < 28:
        return 1.0
    month = int(as_of.month)
    current = float(sales.loc[sales.date.dt.month == month, "quantity"].mean()) if (sales.date.dt.month == month).any() else baseline
    return _bounded(current / baseline if baseline else 1.0, MIN_SEASONALITY, MAX_SEASONALITY)


def calculate_recommendations(sales: pd.DataFrame, inventory: pd.DataFrame, as_of_date: str | None = None, safety_z: float = SAFETY_Z) -> RecalculateResponse:
    sales, inventory = validate_and_normalize(sales, inventory)
    as_of = pd.Timestamp(as_of_date).normalize() if as_of_date else sales["date"].max()
    sales = sales[sales["date"] <= as_of]
    recommendations: list[Recommendation] = []
    warnings: list[str] = []

    for item in inventory.sort_values("sku", kind="mergesort").itertuples(index=False):
        sku_sales = sales[sales.sku == item.sku].copy()
        if sku_sales.empty:
            warnings.append(f"{item.sku}: no sales history; using zero-demand fallback")
            daily = pd.Series([0.0])
            excluded_units = 0.0
            method = "no_history"
            stockout_days = 0.0
            normal = 0.0
        else:
            start, end = sku_sales.date.min(), sku_sales.date.max()
            calendar = pd.date_range(start, end, freq="D")
            grouped = sku_sales.groupby("date", sort=True)["quantity"].sum()
            daily = grouped.reindex(calendar, fill_value=0.0).astype(float)
            stockout_dates = sku_sales.loc[sku_sales.stockout, "date"].drop_duplicates()
            stockout_days = float(len(stockout_dates))
            eligible = sku_sales.loc[~sku_sales.stockout, "quantity"]
            if eligible.empty:
                eligible = sku_sales["quantity"]
            mask, excluded_units, method = _robust_filter(eligible)
            regular = eligible[mask]
            normal = float(regular.mean()) if not regular.empty else float(eligible.mean())
            if normal == 0:
                normal = float(eligible.mean())

            # A large purchase by one anonymized customer is an explicit second guard.
            customer_totals = sku_sales.groupby("customer_id")["quantity"].sum()
            if len(customer_totals) >= 2 and normal > 0:
                customer_cutoff = max(float(customer_totals.quantile(0.75) * 2), normal * 3)
                large_customer_units = float(customer_totals[customer_totals > customer_cutoff].sum())
                excluded_units = max(excluded_units, large_customer_units)

        lost_demand = normal * stockout_days
        growth = _growth_rate(daily)
        seasonality = _seasonality(sku_sales, normal, as_of, item.seasonality_factor)
        lead = int(item.lead_time_days)
        forecast = normal * lead * seasonality * (1.0 + growth) + lost_demand
        # Safety stock must be robust too; a one-day spike must not become a
        # multi-month standard deviation after the order itself was excluded.
        daily_mask, _, _ = _robust_filter(daily)
        stable_daily = daily[daily_mask]
        std_daily = float(stable_daily.std(ddof=1)) if len(stable_daily) > 1 else 0.0
        safety = max(0.0, safety_z * std_daily * np.sqrt(lead)) if lead > 0 else 0.0
        recommended = max(0.0, forecast + safety - float(item.on_hand) - float(item.in_transit))
        available = float(item.on_hand) + float(item.in_transit)
        if recommended > 0 and available < forecast:
            urgency = "high"
        elif recommended > 0:
            urgency = "medium"
        else:
            urgency = "low"
        reasons = [
            Reason(code="demand", text="Базовый средний дневной спрос", value=normal),
            Reason(code="lead_time", text="Спрос на срок поставки", value=forecast),
            Reason(code="safety_stock", text="Страховой запас", value=safety),
            Reason(code="inventory", text="Остаток и товары в пути вычтены из потребности", value=available),
            Reason(code="outliers", text=f"Выбросы обработаны методом {method}; физически не удалялись", value=excluded_units),
        ]
        if stockout_days:
            reasons.append(Reason(code="lost_demand", text="Компенсация спроса за дни stockout", value=lost_demand))
        recommendations.append(Recommendation(
            sku=item.sku, name=None if pd.isna(item.name) else str(item.name), supplier=item.supplier,
            category=None if pd.isna(item.category) else str(item.category), recommended_qty=round(recommended, 4),
            urgency=urgency, on_hand=float(item.on_hand), in_transit=float(item.in_transit), lead_time_days=lead,
            normal_daily_demand=round(max(0.0, normal), 4), stockout_days=stockout_days,
            lost_demand=round(max(0.0, lost_demand), 4), forecast_demand_during_lead_time=round(max(0.0, forecast), 4),
            safety_stock=round(safety, 4), coefficients={"seasonality": round(seasonality, 4), "growth": round(growth, 4), "safety_z": float(safety_z)},
            excluded_units=round(max(0.0, excluded_units), 4), reasons=reasons,
        ))
    grouped = []
    for supplier, rows in pd.DataFrame([r.model_dump() for r in recommendations]).groupby("supplier", sort=True) if recommendations else []:
        grouped.append(SupplierOrder(supplier=supplier, total_recommended_qty=round(float(rows.recommended_qty.sum()), 4), items=[next(r for r in recommendations if r.sku == sku) for sku in rows.sku]))
    return RecalculateResponse(as_of_date=as_of.date().isoformat(), recommendations=recommendations, by_supplier=grouped, warnings=warnings)
