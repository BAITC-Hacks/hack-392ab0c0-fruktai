"""Typed source validation and numeric helpers."""

import math
from datetime import date, timedelta
from typing import Any
from .models import DataValidationError, WorkflowState


def _unique_rows(rows: list[dict[str, str]], key: str, filename: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=2):
        value = _nonempty(row.get(key), f"{filename} row {index} {key}")
        if value in result:
            raise DataValidationError(f"duplicate {key} {value} in {filename}")
        result[value] = dict(row)
    return result


def _known_sku(state: WorkflowState, value: Any, filename: str, row: int) -> str:
    sku = _nonempty(value, f"{filename} row {row} sku")
    if sku not in state.products:
        raise DataValidationError(f"{filename} row {row} references unknown SKU {sku}")
    return sku


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"{label} must be a non-empty string")
    return value.strip()


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


def _number(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise DataValidationError(f"{label} must be a non-negative number") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise DataValidationError(f"{label} must be a non-negative number")
    return parsed


def _boolean(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise DataValidationError(f"{label} must be true or false")


def _date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise DataValidationError(f"{label} must use YYYY-MM-DD") from error


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


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


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _round(value: float) -> float:
    return round(value + 1e-12, 2)


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
