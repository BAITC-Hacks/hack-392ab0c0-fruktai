"""Validation primitives for stored records and source CSV fields."""

import math
from datetime import date
from typing import Any
from .connection import DatabaseError


def _required_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DatabaseError(f"{label} must be an object")
    return value


def _required_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise DatabaseError(f"{label} must be an array")
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatabaseError(f"{label} must be a non-empty string")
    return value.strip()


def _unique_text(value: Any, existing: set[str], filename: str, row_number: int) -> str:
    parsed = _required_text(value, f"{filename}:{row_number}")
    if parsed in existing:
        raise DatabaseError(f"{filename}:{row_number} duplicate key {parsed}")
    existing.add(parsed)
    return parsed


def _known_sku(value: Any, products: set[str], filename: str, row_number: int) -> str:
    sku = _required_text(value, f"{filename}:{row_number} sku")
    if sku not in products:
        raise DatabaseError(f"{filename}:{row_number} unknown SKU {sku}")
    return sku


def _known_unique_sku(
    value: Any,
    products: set[str],
    existing: set[str],
    filename: str,
    row_number: int,
) -> str:
    sku = _known_sku(value, products, filename, row_number)
    if sku in existing:
        raise DatabaseError(f"{filename}:{row_number} duplicate SKU {sku}")
    existing.add(sku)
    return sku


def _csv_integer(value: Any, label: str) -> int:
    text = str(value).strip()
    if not text or not text.isdigit():
        raise DatabaseError(f"{label} must be a non-negative integer")
    return int(text)


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DatabaseError(f"{label} must be a non-negative integer")
    return value


def _csv_number(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise DatabaseError(f"{label} must be a non-negative number") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise DatabaseError(f"{label} must be a non-negative number")
    return parsed


def _csv_boolean(value: Any, label: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise DatabaseError(f"{label} must be true or false")


def _csv_date(value: Any, label: str) -> str:
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise DatabaseError(f"{label} must use YYYY-MM-DD") from error
