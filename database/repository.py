"""SQLite helpers for loading CSV source data and inspecting real runs.

SQLite is optional in the MVP. CSV remains the source of truth and the API
contract remains unchanged.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


SCHEMA_PATH = Path(__file__).with_name("schema.sql")
CSV_HEADERS: dict[str, tuple[str, ...]] = {
    "products": ("sku", "name", "supplier_id", "active"),
    "suppliers": ("supplier_id", "supplier_name", "lead_time_days"),
    "sales": ("date", "sku", "units"),
    "inventory": ("sku", "on_hand"),
    "in_transit": ("sku", "quantity", "expected_date"),
    "stockouts": ("sku", "start_date", "end_date"),
}


class DatabaseError(RuntimeError):
    """Raised when import or persistence cannot preserve the data contract."""


class RecordNotFoundError(DatabaseError):
    """Raised when a requested persisted API resource does not exist."""


@contextmanager
def connect(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path: str | Path) -> Path:
    """Create or update an empty SQLite database from ``schema.sql``."""

    destination = Path(database_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(destination) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(schema)
    return destination


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


def save_calculation(
    database_path: str | Path,
    dataset: str,
    result: dict[str, Any],
    overrides: list[dict[str, Any]] | None = None,
    item_details: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Persist one successful API-compatible calculation response."""

    initialize_database(database_path)
    run_id = _required_text(result.get("run_id"), "result.run_id")
    generated_at = _required_text(result.get("generated_at"), "result.generated_at")
    summary = _required_mapping(result.get("summary"), "result.summary")
    recommendations = _required_list(result.get("recommendations"), "result.recommendations")
    steps = _required_list(result.get("agent_steps"), "result.agent_steps")

    try:
        with connect(database_path) as connection:
            connection.execute(
                """
                INSERT INTO calculation_runs (
                    run_id, dataset, generated_at, status,
                    total_items, total_units_to_order, high_risk_items,
                    anomalies_removed, estimated_stockout_items
                ) VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _required_text(dataset, "dataset"),
                    generated_at,
                    _nonnegative_integer(summary.get("total_items"), "summary.total_items"),
                    _nonnegative_integer(
                        summary.get("total_units_to_order"),
                        "summary.total_units_to_order",
                    ),
                    _nonnegative_integer(
                        summary.get("high_risk_items"), "summary.high_risk_items"
                    ),
                    _nonnegative_integer(
                        summary.get("anomalies_removed"), "summary.anomalies_removed"
                    ),
                    _nonnegative_integer(
                        summary.get("estimated_stockout_items"),
                        "summary.estimated_stockout_items",
                    ),
                ),
            )

            for override in overrides or []:
                connection.execute(
                    """
                    INSERT INTO run_overrides (run_id, sku, on_hand, in_transit)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        _required_text(override.get("sku"), "override.sku"),
                        override.get("on_hand"),
                        override.get("in_transit"),
                    ),
                )

            for index, value in enumerate(recommendations):
                item = _required_mapping(value, f"recommendations[{index}]")
                connection.execute(
                    """
                    INSERT INTO recommendations (
                        run_id, sku, name, supplier_id, supplier_name,
                        recommended_qty, urgency, on_hand, in_transit,
                        lead_time_days, avg_daily_demand, forecast_demand,
                        safety_stock, seasonality_factor, growth_factor,
                        stockout_compensation, outlier_units_removed,
                        days_of_cover, reasons_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        item.get("sku"),
                        item.get("name"),
                        item.get("supplier_id"),
                        item.get("supplier_name"),
                        item.get("recommended_qty"),
                        item.get("urgency"),
                        item.get("on_hand"),
                        item.get("in_transit"),
                        item.get("lead_time_days"),
                        item.get("avg_daily_demand"),
                        item.get("forecast_demand"),
                        item.get("safety_stock"),
                        item.get("seasonality_factor"),
                        item.get("growth_factor"),
                        item.get("stockout_compensation"),
                        item.get("outlier_units_removed"),
                        item.get("days_of_cover"),
                        json.dumps(item.get("reasons", []), ensure_ascii=False),
                    ),
                )

            for order, value in enumerate(steps, start=1):
                step = _required_mapping(value, f"agent_steps[{order - 1}]")
                connection.execute(
                    """
                    INSERT INTO agent_steps (run_id, step_order, step, status, message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        order,
                        step.get("step"),
                        step.get("status"),
                        step.get("message"),
                    ),
                )

            for sku, value in (item_details or {}).items():
                detail = _required_mapping(value, f"item_details.{sku}")
                if detail.get("sku") != sku:
                    raise DatabaseError(f"item detail key mismatch for {sku}")
                history = _required_list(
                    detail.get("history"), f"item_details.{sku}.history"
                )
                for index, point_value in enumerate(history):
                    point = _required_mapping(
                        point_value, f"item_details.{sku}.history[{index}]"
                    )
                    connection.execute(
                        """
                        INSERT INTO item_history (
                            run_id, sku, history_date, units,
                            is_outlier, is_stockout, estimated_lost_units
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            sku,
                            point.get("date"),
                            point.get("units"),
                            int(point.get("is_outlier") is True),
                            int(point.get("is_stockout") is True),
                            point.get("estimated_lost_units"),
                        ),
                    )
    except sqlite3.Error as error:
        raise DatabaseError(f"Cannot save calculation {run_id}: {error}") from error
    return run_id


def latest_recommendations(database_path: str | Path) -> list[dict[str, Any]]:
    return _query(
        database_path,
        """
        SELECT
            supplier_name, sku, name, recommended_qty, urgency,
            on_hand, in_transit, forecast_demand, safety_stock
        FROM latest_recommendations
        ORDER BY
            CASE urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            supplier_name,
            sku
        """,
    )


def supplier_order_summary(database_path: str | Path) -> list[dict[str, Any]]:
    return _query(
        database_path,
        """
        SELECT supplier_id, supplier_name, item_count,
               total_units_to_order, high_risk_items
        FROM supplier_order_summary
        ORDER BY total_units_to_order DESC, supplier_name
        """,
    )


def latest_agent_steps(database_path: str | Path) -> list[dict[str, Any]]:
    return _query(
        database_path,
        """
        SELECT s.step_order, s.step, s.status, s.message
        FROM agent_steps AS s
        JOIN (
            SELECT run_id
            FROM calculation_runs
            ORDER BY generated_at DESC, rowid DESC
            LIMIT 1
        ) AS latest ON latest.run_id = s.run_id
        ORDER BY s.step_order
        """,
    )


def latest_item_detail(
    database_path: str | Path, sku: str, run_id: str | None = None
) -> dict[str, Any]:
    """Return the latest persisted item response in API-contract form."""

    sku_value = _required_text(sku, "sku")
    rows = _query(
        database_path,
        """
        SELECT r.*, c.generated_at
        FROM recommendations AS r
        JOIN calculation_runs AS c ON c.run_id = r.run_id
        WHERE r.sku = ? AND c.status = 'completed'
          AND (? IS NULL OR r.run_id = ?)
        ORDER BY c.generated_at DESC, c.rowid DESC
        LIMIT 1
        """,
        (sku_value, run_id, run_id),
    )
    if not rows:
        raise RecordNotFoundError(f"No calculated item found for SKU {sku_value}")
    recommendation = rows[0]
    history = _query(
        database_path,
        """
        SELECT
            history_date AS date,
            units,
            is_outlier,
            is_stockout,
            estimated_lost_units
        FROM item_history
        WHERE run_id = ? AND sku = ?
        ORDER BY history_date
        """,
        (recommendation["run_id"], sku_value),
    )
    for point in history:
        point["is_outlier"] = bool(point["is_outlier"])
        point["is_stockout"] = bool(point["is_stockout"])
    try:
        reasons = json.loads(recommendation["reasons_json"])
    except (TypeError, json.JSONDecodeError) as error:
        raise DatabaseError(f"Invalid stored reasons for SKU {sku_value}") from error

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
    )
    calculation = {
        field: recommendation[field] for field in calculation_fields
    }
    calculation["reasons"] = reasons
    return {
        "sku": recommendation["sku"],
        "name": recommendation["name"],
        "history": history,
        "calculation": calculation,
    }


def database_stats(database_path: str | Path) -> list[dict[str, Any]]:
    tables = _query(
        database_path,
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """,
    )
    result: list[dict[str, Any]] = []
    with connect(database_path) as connection:
        for table in tables:
            name = table["name"]
            safe_name = name.replace('"', '""')
            count = connection.execute(
                f'SELECT COUNT(*) FROM "{safe_name}"'
            ).fetchone()[0]
            result.append({"table": name, "rows": count})
    return result


def _parse_dataset(source: Path) -> dict[str, list[tuple[Any, ...]]]:
    if not source.is_dir():
        raise DatabaseError(f"Dataset directory not found: {source}")
    raw = {
        name: _read_csv(source / f"{name}.csv", headers)
        for name, headers in CSV_HEADERS.items()
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
                _csv_integer(
                    row.get("quantity"), f"in_transit.csv:{row_number} quantity"
                ),
                _csv_date(
                    row.get("expected_date"),
                    f"in_transit.csv:{row_number} expected_date",
                ),
            )
        )

    stockouts: list[tuple[Any, ...]] = []
    for row_number, row in enumerate(raw["stockouts"], start=2):
        sku = _known_sku(row.get("sku"), product_ids, "stockouts.csv", row_number)
        start = _csv_date(
            row.get("start_date"), f"stockouts.csv:{row_number} start_date"
        )
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


def _delete_sku_rows(
    connection: sqlite3.Connection, table: str, skus: Sequence[str]
) -> None:
    if not skus:
        return
    if table not in {"sales", "in_transit", "stockouts"}:
        raise DatabaseError(f"Unsafe source table: {table}")
    placeholders = ", ".join("?" for _ in skus)
    connection.execute(f"DELETE FROM {table} WHERE sku IN ({placeholders})", tuple(skus))


def _query(
    database_path: str | Path,
    query: str,
    parameters: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    try:
        with connect(database_path) as connection:
            return [dict(row) for row in connection.execute(query, tuple(parameters))]
    except sqlite3.Error as error:
        raise DatabaseError(f"Database query failed: {error}") from error


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


def _unique_text(
    value: Any, existing: set[str], filename: str, row_number: int
) -> str:
    parsed = _required_text(value, f"{filename}:{row_number}")
    if parsed in existing:
        raise DatabaseError(f"{filename}:{row_number} duplicate key {parsed}")
    existing.add(parsed)
    return parsed


def _known_sku(
    value: Any, products: set[str], filename: str, row_number: int
) -> str:
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
