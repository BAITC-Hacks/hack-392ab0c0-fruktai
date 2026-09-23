"""Transparent, deterministic replenishment workflow.

No language model participates in this module. The backend can import
``run_workflow`` directly and expose its result through the fixed API contract.
"""

from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "products": ("sku", "name", "supplier_id", "active"),
    "suppliers": ("supplier_id", "supplier_name", "lead_time_days"),
    "sales": ("date", "sku", "units"),
    "inventory": ("sku", "on_hand"),
    "in_transit": ("sku", "quantity", "expected_date"),
    "stockouts": ("sku", "start_date", "end_date"),
}

WORKFLOW_STEPS = (
    "load_data",
    "validate_data",
    "detect_outliers",
    "estimate_lost_demand",
    "calculate_recommendations",
    "validate_result",
    "save_result",
)


class DataValidationError(ValueError):
    """Raised when source data or an override violates the data contract."""


@dataclass
class WorkflowState:
    dataset_path: Path
    raw: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    products: dict[str, dict[str, Any]] = field(default_factory=dict)
    suppliers: dict[str, dict[str, Any]] = field(default_factory=dict)
    inventory: dict[str, int] = field(default_factory=dict)
    in_transit: dict[str, int] = field(default_factory=dict)
    in_transit_present: set[str] = field(default_factory=set)
    daily_sales: dict[str, dict[date, float]] = field(default_factory=dict)
    stockout_dates: dict[str, set[date]] = field(default_factory=dict)
    outlier_dates: dict[str, set[date]] = field(default_factory=dict)
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    anomaly_count: int = 0


@dataclass(frozen=True)
class WorkflowExecution:
    """Public API response plus internal drill-down data for persistence."""

    response: dict[str, Any]
    item_details: dict[str, dict[str, Any]]


class ReplenishmentOrchestrator:
    """Executes and journals the seven fixed replenishment steps."""

    def __init__(self, safety_stock_days: int = 7, output_dir: str | Path | None = None):
        if safety_stock_days < 0:
            raise ValueError("safety_stock_days must be non-negative")
        self.safety_stock_days = safety_stock_days
        configured_dir = os.getenv("FRUKTAI_RUNS_DIR", "artifacts/runs")
        self.output_dir = Path(output_dir or configured_dir)
        self.steps: list[dict[str, str]] = []

    def run(
        self,
        dataset_path: str | Path,
        overrides: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.run_with_details(dataset_path, overrides).response

    def run_with_details(
        self,
        dataset_path: str | Path,
        overrides: list[dict[str, Any]] | None = None,
    ) -> WorkflowExecution:
        self.steps = []
        state = WorkflowState(dataset_path=Path(dataset_path))
        run_id = str(uuid4())
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        try:
            self._run_step("load_data", lambda: self.load_data(state))
            self._run_step(
                "validate_data", lambda: self.validate_data(state, overrides or [])
            )
            self._run_step("detect_outliers", lambda: self.detect_outliers(state))
            self._run_step(
                "estimate_lost_demand", lambda: self.estimate_lost_demand(state)
            )
            self._run_step(
                "calculate_recommendations",
                lambda: self.calculate_recommendations(state),
            )
            result = self._build_result(run_id, generated_at, state)
            item_details = self._build_item_details(state)
            self._run_step(
                "validate_result",
                lambda: self.validate_result(result, item_details),
            )
            # save_result must be present in the persisted and returned journal.
            self.steps.append(
                {
                    "step": "save_result",
                    "status": "completed",
                    "message": f"Saved calculation run {run_id}",
                }
            )
            result["agent_steps"] = list(self.steps)
            self.save_result(result)
            return WorkflowExecution(response=result, item_details=item_details)
        except Exception as error:
            current_step = WORKFLOW_STEPS[min(len(self.steps), len(WORKFLOW_STEPS) - 1)]
            if not self.steps or self.steps[-1].get("status") != "failed":
                self.steps.append(
                    {"step": current_step, "status": "failed", "message": str(error)}
                )
            self._save_failure_log(run_id, generated_at, error)
            raise

    def _run_step(self, step: str, operation: Any) -> None:
        try:
            message = operation()
        except Exception as error:
            self.steps.append({"step": step, "status": "failed", "message": str(error)})
            raise
        self.steps.append(
            {"step": step, "status": "completed", "message": str(message)}
        )

    def load_data(self, state: WorkflowState) -> str:
        if not state.dataset_path.is_dir():
            raise FileNotFoundError(f"Dataset directory not found: {state.dataset_path}")
        for name, required_headers in REQUIRED_FILES.items():
            path = state.dataset_path / f"{name}.csv"
            if not path.is_file():
                raise FileNotFoundError(f"Required dataset file not found: {path}")
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                headers = tuple(reader.fieldnames or ())
                missing = [header for header in required_headers if header not in headers]
                if missing:
                    raise DataValidationError(
                        f"{path.name} is missing columns: {', '.join(missing)}"
                    )
                state.raw[name] = list(reader)
        return f"Loaded six CSV files from {state.dataset_path}"

    def validate_data(
        self, state: WorkflowState, overrides: list[dict[str, Any]]
    ) -> str:
        state.suppliers = self._unique_rows(
            state.raw["suppliers"], "supplier_id", "suppliers.csv"
        )
        for supplier_id, supplier in state.suppliers.items():
            supplier["supplier_name"] = self._nonempty(
                supplier.get("supplier_name"), f"supplier {supplier_id} name"
            )
            supplier["lead_time_days"] = self._integer(
                supplier.get("lead_time_days"),
                f"supplier {supplier_id} lead_time_days",
            )

        state.products = self._unique_rows(
            state.raw["products"], "sku", "products.csv"
        )
        for sku, product in state.products.items():
            product["name"] = self._nonempty(product.get("name"), f"product {sku} name")
            product["active"] = self._boolean(product.get("active"), f"product {sku} active")
            supplier_id = self._nonempty(
                product.get("supplier_id"), f"product {sku} supplier_id"
            )
            if supplier_id not in state.suppliers:
                raise DataValidationError(
                    f"product {sku} references unknown supplier {supplier_id}"
                )

        inventory_rows = self._unique_rows(
            state.raw["inventory"], "sku", "inventory.csv"
        )
        state.inventory = {
            sku: self._integer(row.get("on_hand"), f"inventory {sku} on_hand")
            for sku, row in inventory_rows.items()
        }

        for sku, product in state.products.items():
            if product["active"] and sku not in state.inventory:
                raise DataValidationError(f"active product {sku} has no inventory row")

        transit: defaultdict[str, int] = defaultdict(int)
        for index, row in enumerate(state.raw["in_transit"], start=2):
            sku = self._known_sku(state, row.get("sku"), "in_transit.csv", index)
            transit[sku] += self._integer(
                row.get("quantity"), f"in_transit.csv row {index} quantity"
            )
            self._date(row.get("expected_date"), f"in_transit.csv row {index} expected_date")
            state.in_transit_present.add(sku)
        state.in_transit = dict(transit)

        sales: defaultdict[str, defaultdict[date, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for index, row in enumerate(state.raw["sales"], start=2):
            sku = self._known_sku(state, row.get("sku"), "sales.csv", index)
            day = self._date(row.get("date"), f"sales.csv row {index} date")
            sales[sku][day] += self._number(
                row.get("units"), f"sales.csv row {index} units"
            )
        state.daily_sales = {sku: dict(days) for sku, days in sales.items()}

        stockouts: defaultdict[str, set[date]] = defaultdict(set)
        for index, row in enumerate(state.raw["stockouts"], start=2):
            sku = self._known_sku(state, row.get("sku"), "stockouts.csv", index)
            start = self._date(
                row.get("start_date"), f"stockouts.csv row {index} start_date"
            )
            end = self._date(
                row.get("end_date"), f"stockouts.csv row {index} end_date"
            )
            if end < start:
                raise DataValidationError(
                    f"stockouts.csv row {index} end_date is before start_date"
                )
            current = start
            while current <= end:
                stockouts[sku].add(current)
                current += timedelta(days=1)
        state.stockout_dates = dict(stockouts)

        self._apply_overrides(state, overrides)
        return f"Validated {len(state.products)} products and {len(overrides)} overrides"

    def detect_outliers(self, state: WorkflowState) -> str:
        state.outlier_dates = {}
        count = 0
        for sku, daily in state.daily_sales.items():
            values = sorted(daily.values())
            if len(values) < 4:
                state.outlier_dates[sku] = set()
                continue
            q1 = self._percentile(values, 0.25)
            q3 = self._percentile(values, 0.75)
            iqr = q3 - q1
            threshold = q3 + 1.5 * iqr
            flagged = {day for day, units in daily.items() if iqr > 0 and units > threshold}
            state.outlier_dates[sku] = flagged
            count += len(flagged)
        state.anomaly_count = count
        return f"Marked {count} daily sales observations as outliers"

    def estimate_lost_demand(self, state: WorkflowState) -> str:
        compensated = 0
        for sku, product in state.products.items():
            if not product["active"]:
                continue
            daily = state.daily_sales.get(sku, {})
            if not daily:
                state.metrics[sku] = self._zero_metrics()
                continue
            last_day = max(daily)
            first_day = max(min(daily), last_day - timedelta(days=27))
            calendar_days = (last_day - first_day).days + 1
            window = self._date_range(first_day, last_day)
            outliers = state.outlier_dates.get(sku, set())
            stockouts = state.stockout_dates.get(sku, set())
            valid_units = sum(
                daily.get(day, 0.0)
                for day in window
                if day not in outliers and day not in stockouts
            )
            baseline = valid_units / calendar_days
            stockout_days = sum(1 for day in window if day in stockouts)
            compensation = baseline * stockout_days
            if compensation > 0:
                compensated += 1

            seasonality = 1.0
            if calendar_days >= 28:
                recent = window[-7:]
                recent_mean = sum(
                    daily.get(day, 0.0)
                    for day in recent
                    if day not in outliers and day not in stockouts
                ) / 7
                if baseline > 0:
                    seasonality = self._clamp(recent_mean / baseline, 0.75, 1.50)

            growth = 1.0
            if calendar_days >= 28:
                recent_14 = window[-14:]
                previous_14 = window[-28:-14]
                recent_valid = [
                    day for day in recent_14 if day not in outliers and day not in stockouts
                ]
                previous_valid = [
                    day
                    for day in previous_14
                    if day not in outliers and day not in stockouts
                ]
                if len(recent_valid) >= 7 and len(previous_valid) >= 7:
                    recent_mean = sum(daily.get(day, 0.0) for day in recent_valid) / 14
                    previous_mean = sum(
                        daily.get(day, 0.0) for day in previous_valid
                    ) / 14
                    if previous_mean > 0:
                        growth = self._clamp(recent_mean / previous_mean, 1.0, 1.30)

            outlier_units = sum(daily.get(day, 0.0) for day in outliers if day in window)
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

    def calculate_recommendations(self, state: WorkflowState) -> str:
        recommendations: list[dict[str, Any]] = []
        for sku in sorted(state.products):
            product = state.products[sku]
            if not product["active"]:
                continue
            supplier = state.suppliers[product["supplier_id"]]
            metrics = state.metrics.get(sku, self._zero_metrics())
            average = metrics["avg_daily_demand"]
            lead_time = supplier["lead_time_days"]
            forecast = (
                average
                * lead_time
                * metrics["seasonality_factor"]
                * metrics["growth_factor"]
            )
            safety_stock = average * self.safety_stock_days
            forecast_value = self._round(forecast)
            safety_stock_value = self._round(safety_stock)
            on_hand = state.inventory[sku]
            in_transit = state.in_transit.get(sku, 0)
            raw_quantity = max(
                0.0,
                forecast_value + safety_stock_value - on_hand - in_transit,
            )
            recommended = math.ceil(raw_quantity)
            available = on_hand + in_transit
            if on_hand == 0 or available < forecast_value:
                urgency = "high"
            elif available < forecast_value + safety_stock_value:
                urgency = "medium"
            else:
                urgency = "low"

            reasons = self._build_reasons(
                state,
                sku,
                recommended,
                urgency,
                metrics,
                forecast,
                safety_stock,
            )
            days_of_cover = available / average if average > 0 else 0.0
            recommendations.append(
                {
                    "sku": sku,
                    "name": product["name"],
                    "supplier_id": product["supplier_id"],
                    "supplier_name": supplier["supplier_name"],
                    "recommended_qty": recommended,
                    "urgency": urgency,
                    "on_hand": on_hand,
                    "in_transit": in_transit,
                    "lead_time_days": lead_time,
                    "avg_daily_demand": self._round(average),
                    "forecast_demand": forecast_value,
                    "safety_stock": safety_stock_value,
                    "seasonality_factor": self._round(metrics["seasonality_factor"]),
                    "growth_factor": self._round(metrics["growth_factor"]),
                    "stockout_compensation": self._round(
                        metrics["stockout_compensation"]
                    ),
                    "outlier_units_removed": self._round(
                        metrics["outlier_units_removed"]
                    ),
                    "days_of_cover": self._round(days_of_cover),
                    "reasons": reasons,
                }
            )
        state.recommendations = recommendations
        return f"Calculated {len(recommendations)} recommendations"

    def validate_result(
        self,
        result: dict[str, Any],
        item_details: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        required = {"run_id", "generated_at", "summary", "recommendations", "agent_steps"}
        missing = required - result.keys()
        if missing:
            raise DataValidationError(f"result is missing fields: {', '.join(sorted(missing))}")
        for item in result["recommendations"]:
            if not isinstance(item["recommended_qty"], int) or item["recommended_qty"] < 0:
                raise DataValidationError(f"invalid recommended_qty for {item.get('sku')}")
            expected_quantity = math.ceil(
                max(
                    0.0,
                    item["forecast_demand"]
                    + item["safety_stock"]
                    - item["on_hand"]
                    - item["in_transit"],
                )
            )
            if item["recommended_qty"] != expected_quantity:
                raise DataValidationError(
                    f"formula mismatch for {item.get('sku')}: "
                    f"expected {expected_quantity}, got {item['recommended_qty']}"
                )
            for field in (
                "avg_daily_demand",
                "forecast_demand",
                "safety_stock",
                "seasonality_factor",
                "growth_factor",
                "stockout_compensation",
                "outlier_units_removed",
                "days_of_cover",
            ):
                value = item[field]
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise DataValidationError(f"invalid {field} for {item.get('sku')}")
        for sku, detail in (item_details or {}).items():
            if detail.get("sku") != sku:
                raise DataValidationError(f"item detail key mismatch for {sku}")
            for point in detail.get("history", []):
                for field in ("units", "estimated_lost_units"):
                    value = point.get(field)
                    if (
                        not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise DataValidationError(
                            f"invalid history {field} for {sku}"
                        )
        return f"Validated {len(result['recommendations'])} recommendations"

    def save_result(self, result: dict[str, Any]) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / f"{result['run_id']}.json"
        with destination.open("w", encoding="utf-8") as target:
            json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")
        return str(destination)

    def _build_result(
        self, run_id: str, generated_at: str, state: WorkflowState
    ) -> dict[str, Any]:
        recommendations = state.recommendations
        return {
            "run_id": run_id,
            "generated_at": generated_at,
            "summary": {
                "total_items": len(recommendations),
                "total_units_to_order": sum(
                    item["recommended_qty"] for item in recommendations
                ),
                "high_risk_items": sum(
                    item["urgency"] == "high" for item in recommendations
                ),
                "anomalies_removed": state.anomaly_count,
                "estimated_stockout_items": sum(
                    item["stockout_compensation"] > 0 for item in recommendations
                ),
            },
            "recommendations": recommendations,
            "agent_steps": list(self.steps),
        }

    def _build_item_details(
        self, state: WorkflowState
    ) -> dict[str, dict[str, Any]]:
        recommendations = {item["sku"]: item for item in state.recommendations}
        details: dict[str, dict[str, Any]] = {}
        calculation_fields = (
            "recommended_qty",
            "on_hand",
            "in_transit",
            "lead_time_days",
            "avg_daily_demand",
            "forecast_demand",
            "safety_stock",
            "seasonality_factor",
            "growth_factor",
            "stockout_compensation",
            "outlier_units_removed",
            "days_of_cover",
            "reasons",
        )
        for sku, recommendation in recommendations.items():
            metrics = state.metrics.get(sku, self._zero_metrics())
            daily = state.daily_sales.get(sku, {})
            outliers = state.outlier_dates.get(sku, set())
            stockouts = state.stockout_dates.get(sku, set())
            start = metrics.get("calculation_start_date")
            end = metrics.get("calculation_end_date")
            if isinstance(start, date) and isinstance(end, date):
                history_days = self._date_range(start, end)
            else:
                history_days = sorted(set(daily) | set(stockouts))
            baseline = float(metrics.get("baseline_daily_demand", 0.0))
            history = [
                {
                    "date": day.isoformat(),
                    "units": self._round(daily.get(day, 0.0)),
                    "is_outlier": day in outliers,
                    "is_stockout": day in stockouts,
                    "estimated_lost_units": self._round(
                        baseline if day in stockouts else 0.0
                    ),
                }
                for day in history_days
            ]
            details[sku] = {
                "sku": sku,
                "name": recommendation["name"],
                "history": history,
                "calculation": {
                    field: recommendation[field] for field in calculation_fields
                },
            }
        return details

    def _apply_overrides(
        self, state: WorkflowState, overrides: list[dict[str, Any]]
    ) -> None:
        seen: set[str] = set()
        allowed = {"sku", "on_hand", "in_transit"}
        for index, override in enumerate(overrides):
            if not isinstance(override, dict):
                raise DataValidationError(f"override {index} must be an object")
            unknown = set(override) - allowed
            if unknown:
                raise DataValidationError(
                    f"override {index} has unknown fields: {', '.join(sorted(unknown))}"
                )
            if "on_hand" not in override and "in_transit" not in override:
                raise DataValidationError(
                    f"override {index} must include on_hand or in_transit"
                )
            sku = self._nonempty(override.get("sku"), f"override {index} sku")
            if sku not in state.products:
                raise DataValidationError(f"override references unknown SKU {sku}")
            if sku in seen:
                raise DataValidationError(f"duplicate override for SKU {sku}")
            seen.add(sku)
            if "on_hand" in override:
                state.inventory[sku] = self._integer(
                    override["on_hand"], f"override {sku} on_hand"
                )
            if "in_transit" in override:
                state.in_transit[sku] = self._integer(
                    override["in_transit"], f"override {sku} in_transit"
                )
                state.in_transit_present.add(sku)

    def _build_reasons(
        self,
        state: WorkflowState,
        sku: str,
        recommended: int,
        urgency: str,
        metrics: dict[str, float],
        forecast: float,
        safety_stock: float,
    ) -> list[str]:
        reasons = [
            f"{urgency.capitalize()} urgency from projected lead-time coverage",
            f"Forecast {self._round(forecast)} plus safety stock {self._round(safety_stock)}",
        ]
        if recommended == 0:
            reasons.append("Available and inbound stock cover the calculated requirement")
        if sku not in state.in_transit_present:
            reasons.append("No in-transit row; controlled fallback uses 0")
        if metrics["calendar_days"] < 28:
            reasons.append("Insufficient seasonal history; seasonality factor uses 1.0")
        if metrics["calendar_days"] < 7:
            reasons.append("Fewer than 7 days of history; all available history is used")
        if metrics["stockout_compensation"] > 0:
            reasons.append(
                f"Estimated {self._round(metrics['stockout_compensation'])} units lost during stockouts"
            )
        if metrics["outlier_units_removed"] > 0:
            reasons.append(
                f"Removed {self._round(metrics['outlier_units_removed'])} outlier units"
            )
        if metrics["avg_daily_demand"] == 0:
            reasons.append("No usable demand history; days of cover is reported as 0.0")
        return reasons

    def _save_failure_log(
        self, run_id: str, generated_at: str, error: Exception
    ) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{run_id}.failed.json"
            payload = {
                "run_id": run_id,
                "generated_at": generated_at,
                "error": str(error),
                "agent_steps": self.steps,
            }
            with path.open("w", encoding="utf-8") as target:
                json.dump(payload, target, ensure_ascii=False, indent=2, allow_nan=False)
                target.write("\n")
        except OSError:
            # Preserve the original data/calculation failure.
            return

    @staticmethod
    def _unique_rows(
        rows: list[dict[str, str]], key: str, filename: str
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows, start=2):
            value = ReplenishmentOrchestrator._nonempty(
                row.get(key), f"{filename} row {index} {key}"
            )
            if value in result:
                raise DataValidationError(f"duplicate {key} {value} in {filename}")
            result[value] = dict(row)
        return result

    @staticmethod
    def _known_sku(
        state: WorkflowState, value: Any, filename: str, row: int
    ) -> str:
        sku = ReplenishmentOrchestrator._nonempty(value, f"{filename} row {row} sku")
        if sku not in state.products:
            raise DataValidationError(f"{filename} row {row} references unknown SKU {sku}")
        return sku

    @staticmethod
    def _nonempty(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DataValidationError(f"{label} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _integer(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise DataValidationError(f"{label} must be a non-negative integer")
        try:
            if isinstance(value, str) and not value.strip():
                raise ValueError
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise DataValidationError(f"{label} must be a non-negative integer") from error
        if parsed < 0 or (isinstance(value, float) and not value.is_integer()):
            raise DataValidationError(f"{label} must be a non-negative integer")
        if isinstance(value, str) and str(parsed) != value.strip():
            raise DataValidationError(f"{label} must be a non-negative integer")
        return parsed

    @staticmethod
    def _number(value: Any, label: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as error:
            raise DataValidationError(f"{label} must be a non-negative number") from error
        if not math.isfinite(parsed) or parsed < 0:
            raise DataValidationError(f"{label} must be a non-negative number")
        return parsed

    @staticmethod
    def _boolean(value: Any, label: str) -> bool:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise DataValidationError(f"{label} must be true or false")

    @staticmethod
    def _date(value: Any, label: str) -> date:
        try:
            return date.fromisoformat(str(value))
        except ValueError as error:
            raise DataValidationError(f"{label} must use YYYY-MM-DD") from error

    @staticmethod
    def _date_range(start: date, end: date) -> list[date]:
        return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float:
        if not values:
            return 0.0
        position = (len(values) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return values[lower]
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    @staticmethod
    def _round(value: float) -> float:
        return round(value + 1e-12, 2)

    @staticmethod
    def _zero_metrics() -> dict[str, Any]:
        return {
            "calendar_days": 0.0,
            "avg_daily_demand": 0.0,
            "stockout_compensation": 0.0,
            "seasonality_factor": 1.0,
            "growth_factor": 1.0,
            "outlier_units_removed": 0.0,
            "baseline_daily_demand": 0.0,
            "calculation_start_date": None,
            "calculation_end_date": None,
        }


def run_workflow(
    dataset_path: str | Path,
    overrides: list[dict[str, Any]] | None = None,
    *,
    safety_stock_days: int = 7,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the complete workflow and return an API-compatible response."""

    return run_workflow_with_details(
        dataset_path=dataset_path,
        overrides=overrides,
        safety_stock_days=safety_stock_days,
        output_dir=output_dir,
    ).response


def run_workflow_with_details(
    dataset_path: str | Path,
    overrides: list[dict[str, Any]] | None = None,
    *,
    safety_stock_days: int = 7,
    output_dir: str | Path | None = None,
) -> WorkflowExecution:
    """Run the workflow and retain item drill-down data for persistence."""

    return ReplenishmentOrchestrator(
        safety_stock_days=safety_stock_days,
        output_dir=output_dir,
    ).run_with_details(dataset_path=dataset_path, overrides=overrides)
