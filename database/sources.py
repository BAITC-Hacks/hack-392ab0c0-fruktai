"""Validate and synchronize the six source tables in one transaction."""

import csv
import sqlite3
from pathlib import Path
from typing import Any, Sequence
from .connection import connect, initialize_database, DatabaseError
from .validation import (
    _required_text,
    _unique_text,
    _known_sku,
    _known_unique_sku,
    _csv_integer,
    _csv_number,
    _csv_boolean,
    _csv_date,
)

CSV_HEADERS: dict[str, tuple[str, ...]] = {
    "products": ("sku", "name", "supplier_id", "active"),
    "suppliers": ("supplier_id", "supplier_name", "lead_time_days"),
    "sales": ("date", "sku", "units"),
    "inventory": ("sku", "on_hand"),
    "in_transit": ("sku", "quantity", "expected_date"),
    "stockouts": ("sku", "start_date", "end_date"),
}


def load_csv_dataset(database_path: str | Path, dataset_path: str | Path) -> dict[str, int]:
    """Validate and load all six CSV files in one database transaction."""

    source = Path(dataset_path)
    parsed = _parse_dataset(source)
    initialize_database(database_path)

    try:
        with connect(database_path) as connection:
            connection.executemany(
                """
                INSERT INTO suppliers (supplier_id, supplier_name, lead_time_days)
                VALUES (?, ?, ?)
                ON CONFLICT (supplier_id) DO UPDATE SET
                    supplier_name = excluded.supplier_name,
                    lead_time_days = excluded.lead_time_days
                """,
                parsed["suppliers"],
            )
            connection.executemany(
                """
                INSERT INTO products (sku, name, supplier_id, active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (sku) DO UPDATE SET
                    name = excluded.name,
                    supplier_id = excluded.supplier_id,
                    active = excluded.active
                """,
                parsed["products"],
            )
            connection.executemany(
                """
                INSERT INTO inventory (sku, on_hand)
                VALUES (?, ?)
                ON CONFLICT (sku) DO UPDATE SET
                    on_hand = excluded.on_hand,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                parsed["inventory"],
            )

            skus = [row[0] for row in parsed["products"]]
            _delete_sku_rows(connection, "sales", skus)
            _delete_sku_rows(connection, "in_transit", skus)
            _delete_sku_rows(connection, "stockouts", skus)

            connection.executemany(
                "INSERT INTO sales (sale_date, sku, units) VALUES (?, ?, ?)",
                parsed["sales"],
            )
            connection.executemany(
                """
                INSERT INTO in_transit (sku, quantity, expected_date)
                VALUES (?, ?, ?)
                """,
                parsed["in_transit"],
            )
            connection.executemany(
                """
                INSERT INTO stockouts (sku, start_date, end_date)
                VALUES (?, ?, ?)
                """,
                parsed["stockouts"],
            )
    except sqlite3.Error as error:
        raise DatabaseError(f"Cannot load dataset {source}: {error}") from error

    return {name: len(rows) for name, rows in parsed.items()}


def _parse_dataset(source: Path) -> dict[str, list[tuple[Any, ...]]]:
    if not source.is_dir():
        raise DatabaseError(f"Dataset directory not found: {source}")
    raw = {
        name: _read_csv(source / f"{name}.csv", headers) for name, headers in CSV_HEADERS.items()
    }

    suppliers: list[tuple[Any, ...]] = []
    supplier_ids: set[str] = set()
    for row_number, row in enumerate(raw["suppliers"], start=2):
        supplier_id = _unique_text(
            row.get("supplier_id"), supplier_ids, "suppliers.csv", row_number
        )
        suppliers.append(
            (
                supplier_id,
                _required_text(row.get("supplier_name"), f"suppliers.csv:{row_number}"),
                _csv_integer(
                    row.get("lead_time_days"),
                    f"suppliers.csv:{row_number} lead_time_days",
                ),
            )
        )

    products: list[tuple[Any, ...]] = []
    product_ids: set[str] = set()
    active_products: set[str] = set()
    for row_number, row in enumerate(raw["products"], start=2):
        sku = _unique_text(row.get("sku"), product_ids, "products.csv", row_number)
        supplier_id = _required_text(
            row.get("supplier_id"), f"products.csv:{row_number} supplier_id"
        )
        if supplier_id not in supplier_ids:
            raise DatabaseError(f"products.csv:{row_number} unknown supplier {supplier_id}")
        active = _csv_boolean(row.get("active"), f"products.csv:{row_number} active")
        if active:
            active_products.add(sku)
        products.append(
            (
                sku,
                _required_text(row.get("name"), f"products.csv:{row_number} name"),
                supplier_id,
                int(active),
            )
        )

    inventory: list[tuple[Any, ...]] = []
    inventory_ids: set[str] = set()
    for row_number, row in enumerate(raw["inventory"], start=2):
        sku = _known_unique_sku(
            row.get("sku"), product_ids, inventory_ids, "inventory.csv", row_number
        )
        inventory.append(
            (
                sku,
                _csv_integer(row.get("on_hand"), f"inventory.csv:{row_number} on_hand"),
            )
        )
    missing_inventory = active_products - inventory_ids
    if missing_inventory:
        raise DatabaseError(
            f"Active products without inventory: {', '.join(sorted(missing_inventory))}"
        )

    sales: list[tuple[Any, ...]] = []
    for row_number, row in enumerate(raw["sales"], start=2):
        sku = _known_sku(row.get("sku"), product_ids, "sales.csv", row_number)
        sales.append(
            (
                _csv_date(row.get("date"), f"sales.csv:{row_number} date"),
                sku,
                _csv_number(row.get("units"), f"sales.csv:{row_number} units"),
            )
        )

    in_transit: list[tuple[Any, ...]] = []
    for row_number, row in enumerate(raw["in_transit"], start=2):
        sku = _known_sku(row.get("sku"), product_ids, "in_transit.csv", row_number)
        in_transit.append(
            (
                sku,
                _csv_integer(row.get("quantity"), f"in_transit.csv:{row_number} quantity"),
                _csv_date(
                    row.get("expected_date"),
                    f"in_transit.csv:{row_number} expected_date",
                ),
            )
        )

    stockouts: list[tuple[Any, ...]] = []
    for row_number, row in enumerate(raw["stockouts"], start=2):
        sku = _known_sku(row.get("sku"), product_ids, "stockouts.csv", row_number)
        start = _csv_date(row.get("start_date"), f"stockouts.csv:{row_number} start_date")
        end = _csv_date(row.get("end_date"), f"stockouts.csv:{row_number} end_date")
        if end < start:
            raise DatabaseError(f"stockouts.csv:{row_number} end_date is before start_date")
        stockouts.append((sku, start, end))

    return {
        "suppliers": suppliers,
        "products": products,
        "inventory": inventory,
        "sales": sales,
        "in_transit": in_transit,
        "stockouts": stockouts,
    }


def _read_csv(path: Path, required_headers: Sequence[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise DatabaseError(f"Required CSV file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        headers = reader.fieldnames or []
        missing = [header for header in required_headers if header not in headers]
        if missing:
            raise DatabaseError(f"{path.name} missing columns: {', '.join(missing)}")
        return list(reader)


def _delete_sku_rows(connection: sqlite3.Connection, table: str, skus: Sequence[str]) -> None:
    if not skus:
        return
    if table not in {"sales", "in_transit", "stockouts"}:
        raise DatabaseError(f"Unsafe source table: {table}")
    placeholders = ", ".join("?" for _ in skus)
    connection.execute(f"DELETE FROM {table} WHERE sku IN ({placeholders})", tuple(skus))
