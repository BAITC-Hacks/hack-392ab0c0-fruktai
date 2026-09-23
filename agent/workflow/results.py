"""Build and verify the public response and item history."""

import math
from datetime import date
from typing import Any
from .models import DataValidationError, WorkflowState
from .primitives import _zero_metrics, _date_range, _round


def validate_result(
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
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise DataValidationError(f"invalid history {field} for {sku}")
    return f"Validated {len(result['recommendations'])} recommendations"


def _build_result(
    run_id: str, generated_at: str, state: WorkflowState, steps: list[dict[str, str]]
) -> dict[str, Any]:
    recommendations = state.recommendations
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "summary": {
            "total_items": len(recommendations),
            "total_units_to_order": sum(item["recommended_qty"] for item in recommendations),
            "high_risk_items": sum(item["urgency"] == "high" for item in recommendations),
            "anomalies_removed": state.anomaly_count,
            "estimated_stockout_items": sum(
                item["stockout_compensation"] > 0 for item in recommendations
            ),
        },
        "recommendations": recommendations,
        "agent_steps": list(steps),
    }


def _build_item_details(state: WorkflowState) -> dict[str, dict[str, Any]]:
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
        metrics = state.metrics.get(sku, _zero_metrics())
        daily = state.daily_sales.get(sku, {})
        outliers = state.outlier_dates.get(sku, set())
        stockouts = state.stockout_dates.get(sku, set())
        start = metrics.get("calculation_start_date")
        end = metrics.get("calculation_end_date")
        if isinstance(start, date) and isinstance(end, date):
            history_days = _date_range(start, end)
        else:
            history_days = sorted(set(daily) | set(stockouts))
        baseline = float(metrics.get("baseline_daily_demand", 0.0))
        history = [
            {
                "date": day.isoformat(),
                "units": _round(daily.get(day, 0.0)),
                "is_outlier": day in outliers or day in state.client_outlier_dates.get(sku, set()),
                "is_stockout": day in stockouts,
                "estimated_lost_units": _round(baseline if day in stockouts else 0.0),
            }
            for day in history_days
        ]
        details[sku] = {
            "sku": sku,
            "name": recommendation["name"],
            "history": history,
            "calculation": {field: recommendation[field] for field in calculation_fields},
        }
    return details
