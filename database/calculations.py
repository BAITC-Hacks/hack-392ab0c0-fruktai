"""Persist one immutable calculation with overrides, history and steps."""

import json
import sqlite3
from pathlib import Path
from typing import Any
from .connection import connect, initialize_database, DatabaseError
from .validation import _required_text, _required_mapping, _required_list, _nonnegative_integer


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
                    _nonnegative_integer(summary.get("high_risk_items"), "summary.high_risk_items"),
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
                history = _required_list(detail.get("history"), f"item_details.{sku}.history")
                for index, point_value in enumerate(history):
                    point = _required_mapping(point_value, f"item_details.{sku}.history[{index}]")
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
