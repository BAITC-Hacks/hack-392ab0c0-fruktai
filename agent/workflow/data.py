"""Load source CSV tables, validate relationships and apply explicit overrides."""

import csv
from collections import defaultdict
from datetime import date
from typing import Any
from .models import DataValidationError, REQUIRED_FILES, WorkflowState
from .primitives import (
    _unique_rows,
    _nonempty,
    _integer,
    _boolean,
    _date,
    _known_sku,
    _number,
    _date_range,
)


def load_data(state: WorkflowState) -> str:
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
                raise DataValidationError(f"{path.name} is missing columns: {', '.join(missing)}")
            state.raw[name] = list(reader)
    return f"Loaded six CSV files from {state.dataset_path}"


def validate_data(state: WorkflowState, overrides: list[dict[str, Any]]) -> str:
    state.suppliers = _unique_rows(state.raw["suppliers"], "supplier_id", "suppliers.csv")
    for supplier_id, supplier in state.suppliers.items():
        supplier["supplier_name"] = _nonempty(
            supplier.get("supplier_name"), f"supplier {supplier_id} name"
        )
        supplier["lead_time_days"] = _integer(
            supplier.get("lead_time_days"),
            f"supplier {supplier_id} lead_time_days",
        )

    state.products = _unique_rows(state.raw["products"], "sku", "products.csv")
    for sku, product in state.products.items():
        product["name"] = _nonempty(product.get("name"), f"product {sku} name")
        product["active"] = _boolean(product.get("active"), f"product {sku} active")
        supplier_id = _nonempty(product.get("supplier_id"), f"product {sku} supplier_id")
        if supplier_id not in state.suppliers:
            raise DataValidationError(f"product {sku} references unknown supplier {supplier_id}")

    inventory_rows = _unique_rows(state.raw["inventory"], "sku", "inventory.csv")
    state.inventory = {
        sku: _integer(row.get("on_hand"), f"inventory {sku} on_hand")
        for sku, row in inventory_rows.items()
    }

    for sku, product in state.products.items():
        if product["active"] and sku not in state.inventory:
            raise DataValidationError(f"active product {sku} has no inventory row")

    transit: defaultdict[str, int] = defaultdict(int)
    for index, row in enumerate(state.raw["in_transit"], start=2):
        sku = _known_sku(state, row.get("sku"), "in_transit.csv", index)
        transit[sku] += _integer(row.get("quantity"), f"in_transit.csv row {index} quantity")
        _date(row.get("expected_date"), f"in_transit.csv row {index} expected_date")
        state.in_transit_present.add(sku)
    state.in_transit = dict(transit)

    sales: defaultdict[str, defaultdict[date, float]] = defaultdict(lambda: defaultdict(float))
    for index, row in enumerate(state.raw["sales"], start=2):
        sku = _known_sku(state, row.get("sku"), "sales.csv", index)
        day = _date(row.get("date"), f"sales.csv row {index} date")
        sales[sku][day] += _number(row.get("units"), f"sales.csv row {index} units")
    state.daily_sales = {sku: dict(days) for sku, days in sales.items()}

    stockouts: defaultdict[str, set[date]] = defaultdict(set)
    for index, row in enumerate(state.raw["stockouts"], start=2):
        sku = _known_sku(state, row.get("sku"), "stockouts.csv", index)
        start = _date(row.get("start_date"), f"stockouts.csv row {index} start_date")
        end = _date(row.get("end_date"), f"stockouts.csv row {index} end_date")
        if end < start:
            raise DataValidationError(f"stockouts.csv row {index} end_date is before start_date")
        stockouts[sku].update(_date_range(start, end))
    state.stockout_dates = dict(stockouts)

    _apply_overrides(state, overrides)
    return f"Validated {len(state.products)} products and {len(overrides)} overrides"


def _apply_overrides(state: WorkflowState, overrides: list[dict[str, Any]]) -> None:
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
            raise DataValidationError(f"override {index} must include on_hand or in_transit")
        sku = _nonempty(override.get("sku"), f"override {index} sku")
        if sku not in state.products:
            raise DataValidationError(f"override references unknown SKU {sku}")
        if sku in seen:
            raise DataValidationError(f"duplicate override for SKU {sku}")
        seen.add(sku)
        if "on_hand" in override:
            state.inventory[sku] = _integer(override["on_hand"], f"override {sku} on_hand")
        if "in_transit" in override:
            state.in_transit[sku] = _integer(override["in_transit"], f"override {sku} in_transit")
            state.in_transit_present.add(sku)
