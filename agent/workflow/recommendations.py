"""Convert demand and availability into explainable order quantities."""

import math
from typing import Any
from .models import WorkflowState
from .primitives import _zero_metrics, _round


def calculate_recommendations(state: WorkflowState, safety_stock_days: int = 7) -> str:
    recommendations: list[dict[str, Any]] = []
    for sku in sorted(state.products):
        product = state.products[sku]
        if not product["active"]:
            continue
        supplier = state.suppliers[product["supplier_id"]]
        metrics = state.metrics.get(sku, _zero_metrics())
        average = metrics["avg_daily_demand"]
        lead_time = supplier["lead_time_days"]
        forecast = average * lead_time * metrics["seasonality_factor"] * metrics["growth_factor"]
        safety_stock = average * safety_stock_days
        forecast_value = _round(forecast)
        safety_stock_value = _round(safety_stock)
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

        reasons = _build_reasons(
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
                "avg_daily_demand": _round(average),
                "forecast_demand": forecast_value,
                "safety_stock": safety_stock_value,
                "seasonality_factor": _round(metrics["seasonality_factor"]),
                "growth_factor": _round(metrics["growth_factor"]),
                "stockout_compensation": _round(metrics["stockout_compensation"]),
                "outlier_units_removed": _round(metrics["outlier_units_removed"]),
                "days_of_cover": _round(days_of_cover),
                "reasons": reasons,
            }
        )
    state.recommendations = recommendations
    return f"Calculated {len(recommendations)} recommendations"


def _build_reasons(
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
        f"Forecast {_round(forecast)} plus safety stock {_round(safety_stock)}",
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
            f"Estimated {_round(metrics['stockout_compensation'])} units lost during stockouts"
        )
    if metrics["outlier_units_removed"] > 0:
        reasons.append(f"Removed {_round(metrics['outlier_units_removed'])} outlier units")
    if metrics["avg_daily_demand"] == 0:
        reasons.append("No usable demand history; days of cover is reported as 0.0")
    return reasons
