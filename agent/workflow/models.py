"""Workflow contracts and in-memory state; no I/O or decisions."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

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
    regular_daily_sales: dict[str, dict[date, float]] = field(default_factory=dict)
    client_outlier_dates: dict[str, set[date]] = field(default_factory=dict)
    removed_by_day: dict[str, dict[date, float]] = field(default_factory=dict)
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
