"""Read models for the dashboard, item drill-down and local inspection."""

import json
from pathlib import Path
from typing import Any
from .connection import connect, _query, DatabaseError, RecordNotFoundError
from .validation import _required_text


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
    calculation = {field: recommendation[field] for field in calculation_fields}
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
            count = connection.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
            result.append({"table": name, "rows": count})
    return result
