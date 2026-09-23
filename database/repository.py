"""Transactional SQLite persistence for source snapshots and recommendation runs."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class DatabaseError(RuntimeError):
    """Raised when persistence or retrieval fails."""


def database_path() -> Path:
    return Path(os.getenv("FRUKTAI_DATABASE_PATH", "artifacts/fruktai.sqlite"))


@contextmanager
def _connect(path: str | Path | None = None):
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _connect(target) as connection:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            recommendation_columns = {row["name"] for row in connection.execute("PRAGMA table_info(recommendations)")}
            if "calculation_json" not in recommendation_columns:
                connection.execute("ALTER TABLE recommendations ADD COLUMN calculation_json TEXT NOT NULL DEFAULT '{}'")
            override_columns = {row["name"] for row in connection.execute("PRAGMA table_info(run_overrides)")}
            for column in ("backorders", "reserved"):
                if column not in override_columns:
                    connection.execute(f"ALTER TABLE run_overrides ADD COLUMN {column} REAL")
    except sqlite3.Error as error:
        raise DatabaseError(f"SQLite initialization failed: {error}") from error
    return target


def _supplier_id(name: str) -> str:
    return name.strip() or "Unknown supplier"


def persist_run(sales: pd.DataFrame, inventory: pd.DataFrame, response: dict, overrides: dict | None = None, transit: pd.DataFrame | None = None, path: str | Path | None = None, dataset: str = "uploaded_csv") -> str:
    """Persist input snapshot and result atomically; original uploads remain untouched."""
    target = initialize_database(path)
    run_id = str(uuid4())
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    recommendations = response.get("recommendations", [])
    try:
        with _connect(target) as connection:
            supplier_rows = {}
            for row in inventory.to_dict("records"):
                supplier_name = str(row.get("supplier", row.get("supplier_name", "Unknown supplier")))
                supplier_id = str(row.get("supplier_id") or _supplier_id(supplier_name))
                supplier_rows[supplier_id] = (supplier_id, supplier_name, int(row["lead_time_days"]))
            connection.executemany(
                "INSERT INTO suppliers VALUES (?, ?, ?) ON CONFLICT(supplier_id) DO UPDATE SET supplier_name=excluded.supplier_name, lead_time_days=excluded.lead_time_days",
                supplier_rows.values(),
            )
            skus = []
            for row in inventory.to_dict("records"):
                sku = str(row["sku"]).strip().upper()
                skus.append(sku)
                name_value = row.get("name")
                name = sku if pd.isna(name_value) else str(name_value)
                supplier_name = str(row.get("supplier", row.get("supplier_name", "Unknown supplier")))
                sid = str(row.get("supplier_id") or _supplier_id(supplier_name))
                connection.execute("INSERT INTO products(sku,name,supplier_id,active) VALUES(?,?,?,1) ON CONFLICT(sku) DO UPDATE SET name=excluded.name,supplier_id=excluded.supplier_id,active=1", (sku, name, sid))
                connection.execute("INSERT INTO inventory(sku,on_hand,updated_at) VALUES(?,?,?) ON CONFLICT(sku) DO UPDATE SET on_hand=excluded.on_hand,updated_at=excluded.updated_at", (sku, float(row["on_hand"]), generated))
                connection.execute("DELETE FROM sales WHERE sku=?", (sku,))
                connection.execute("DELETE FROM in_transit WHERE sku=?", (sku,))
                connection.execute("DELETE FROM stockouts WHERE sku=?", (sku,))
                sales_rows = sales.loc[sales.sku.astype(str).str.strip().str.upper() == sku]
                connection.executemany("INSERT INTO sales(sale_date,sku,units) VALUES(?,?,?)", [(pd.Timestamp(s.date).date().isoformat(), sku, float(s.quantity)) for s in sales_rows.itertuples()])
                if transit is not None and not transit.empty:
                    shipment_rows = transit.loc[transit.sku.astype(str).str.strip().str.upper() == sku]
                    connection.executemany("INSERT INTO in_transit(sku,quantity,expected_date) VALUES(?,?,?)", [(sku, float(shipment.quantity), pd.Timestamp(shipment.expected_date).date().isoformat()) for shipment in shipment_rows.itertuples()])
                stockout_mask = sales_rows["stockout"].astype(bool) if "stockout" in sales_rows else pd.Series(False, index=sales_rows.index)
                for day in sales_rows.loc[stockout_mask, "date"].drop_duplicates():
                    value = pd.Timestamp(day).date().isoformat()
                    connection.execute("INSERT INTO stockouts(sku,start_date,end_date) VALUES(?,?,?)", (sku, value, value))

            qty = sum(float(item["recommended_qty"]) for item in recommendations)
            connection.execute("""INSERT INTO calculation_runs(
                run_id,dataset,generated_at,status,total_items,total_units_to_order,
                high_risk_items,anomalies_removed,estimated_stockout_items
                ) VALUES(?,?,?,'completed',?,?,?, ?,?)""", (run_id, dataset, generated, len(recommendations), qty, sum(item["urgency"] == "high" for item in recommendations), response.get("summary", {}).get("anomalies_removed", 0), response.get("summary", {}).get("estimated_stockout_items", 0)))
            for sku, fields in (overrides or {}).items():
                connection.execute("INSERT INTO run_overrides(run_id,sku,on_hand,in_transit,backorders,reserved) VALUES(?,?,?,?,?,?)", (run_id, sku, fields.get("on_hand"), fields.get("in_transit"), fields.get("backorders"), fields.get("reserved")))
            for index, step in enumerate(response.get("agent_steps", []), start=1):
                connection.execute("INSERT INTO agent_steps(run_id,step_order,step,status,message) VALUES(?,?,?,?,?)", (run_id, index, step["step"], step["status"], step["message"]))
            for item in recommendations:
                sid = str(item.get("supplier_id") or _supplier_id(item.get("supplier_name", item.get("supplier", "Unknown supplier"))))
                supplier_name = item.get("supplier_name", item.get("supplier", "Unknown supplier"))
                avg_demand = item.get("avg_daily_demand", item.get("normal_daily_demand", 0.0))
                forecast = item.get("forecast_demand", item.get("forecast_demand_during_lead_time", 0.0))
                stockout_compensation = item.get("stockout_compensation", item.get("lost_demand", 0.0))
                excluded_units = item.get("outlier_units_removed", item.get("excluded_units", 0.0))
                connection.execute(
                    """INSERT INTO recommendations(
                        run_id,sku,name,supplier_id,supplier_name,recommended_qty,urgency,
                        on_hand,in_transit,lead_time_days,avg_daily_demand,forecast_demand,
                        safety_stock,seasonality_factor,growth_factor,stockout_compensation,
                        outlier_units_removed,days_of_cover,reasons_json,calculation_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, item["sku"], item.get("name") or item["sku"], sid, supplier_name, item["recommended_qty"], item["urgency"], item["on_hand"], item["in_transit"], item["lead_time_days"], avg_demand, forecast, item["safety_stock"], item.get("seasonality_factor", item.get("coefficients", {}).get("seasonality", 1.0)), item.get("growth_factor", 1.0 + item.get("coefficients", {}).get("growth", 0.0)), stockout_compensation, excluded_units, item["days_of_cover"], json.dumps(item.get("reasons", []), ensure_ascii=False), json.dumps(item.model_dump() if hasattr(item, "model_dump") else item, ensure_ascii=False)),
                )
                sku = item["sku"]
                daily_sales = sales.loc[sales.sku.astype(str).str.strip().str.upper() == sku].copy()
                if not daily_sales.empty:
                    daily_sales["date"] = pd.to_datetime(daily_sales["date"], errors="coerce").dt.normalize()
                    totals = daily_sales.groupby("date", sort=True)["quantity"].sum()
                    stockout_dates = set(daily_sales.loc[daily_sales.get("stockout", False).astype(bool), "date"]) if "stockout" in daily_sales else set()
                    compensation_per_day = float(stockout_compensation) / max(1, len(stockout_dates))
                    for day in pd.date_range(totals.index.min(), totals.index.max(), freq="D"):
                        is_stockout = day in stockout_dates
                        connection.execute("INSERT INTO item_history VALUES(?,?,?,?,?,?,?)", (run_id, sku, day.date().isoformat(), float(totals.get(day, 0.0)), 0, int(is_stockout), compensation_per_day if is_stockout else 0.0))
    except (sqlite3.Error, KeyError, TypeError, ValueError) as error:
        raise DatabaseError(f"Cannot persist recommendation run: {error}") from error
    return run_id


def latest_item(sku: str, path: str | Path | None = None) -> dict:
    target = initialize_database(path)
    try:
        with _connect(target) as connection:
            row = connection.execute("SELECT calculation_json FROM latest_recommendations WHERE upper(sku)=upper(?)", (sku.strip(),)).fetchone()
        if row is None:
            raise LookupError(sku)
        return json.loads(row["calculation_json"])
    except LookupError:
        raise
    except (sqlite3.Error, json.JSONDecodeError) as error:
        raise DatabaseError(f"Cannot load item from SQLite: {error}") from error


def latest_item_detail(sku: str, path: str | Path | None = None) -> dict:
    target = initialize_database(path)
    try:
        with _connect(target) as connection:
            row = connection.execute("""SELECT r.run_id,r.name,r.calculation_json
                FROM recommendations r JOIN calculation_runs c ON c.run_id=r.run_id
                WHERE upper(r.sku)=upper(?) AND c.status='completed'
                ORDER BY c.generated_at DESC,c.rowid DESC LIMIT 1""", (sku.strip(),)).fetchone()
            if row is None:
                raise LookupError(sku)
            history = [dict(point) for point in connection.execute("SELECT history_date AS date,units,is_outlier,is_stockout,estimated_lost_units FROM item_history WHERE run_id=? AND sku=? ORDER BY history_date", (row["run_id"], sku.strip().upper()))]
        for point in history:
            point["is_outlier"] = bool(point["is_outlier"])
            point["is_stockout"] = bool(point["is_stockout"])
        return {"sku": sku.strip().upper(), "name": row["name"], "history": history, "calculation": json.loads(row["calculation_json"])}
    except LookupError:
        raise
    except (sqlite3.Error, json.JSONDecodeError) as error:
        raise DatabaseError(f"Cannot load item detail from SQLite: {error}") from error


def latest_summary(path: str | Path | None = None) -> dict:
    target = initialize_database(path)
    try:
        with _connect(target) as connection:
            run = connection.execute("SELECT * FROM calculation_runs WHERE status='completed' ORDER BY generated_at DESC,rowid DESC LIMIT 1").fetchone()
            if run is None:
                return {}
            approval = connection.execute("SELECT approved FROM approvals WHERE run_id=?", (run["run_id"],)).fetchone()
            aggregates = connection.execute("""SELECT
                COUNT(*) AS sku_count,
                SUM(CASE WHEN recommended_qty > 0 THEN 1 ELSE 0 END) AS items_to_order,
                SUM(CASE WHEN urgency='high' THEN 1 ELSE 0 END) AS high_urgency_count,
                SUM(CASE WHEN urgency='medium' THEN 1 ELSE 0 END) AS medium_urgency_count,
                SUM(CASE WHEN urgency='low' THEN 1 ELSE 0 END) AS low_urgency_count,
                COALESCE(SUM(recommended_qty),0) AS total_recommended_qty,
                COUNT(DISTINCT supplier_id) AS supplier_count,
                COALESCE(SUM(outlier_units_removed),0) AS excluded_outlier_units,
                SUM(CASE WHEN stockout_compensation > 0 THEN 1 ELSE 0 END) AS stockout_items
                FROM recommendations WHERE run_id=?""", (run["run_id"],)).fetchone()
            return {**dict(aggregates), "approved": bool(approval["approved"]) if approval else False}
    except sqlite3.Error as error:
        raise DatabaseError(f"Cannot load SQLite summary: {error}") from error


def set_approval(approved: bool, note: str | None = None, path: str | Path | None = None) -> None:
    target = initialize_database(path)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        with _connect(target) as connection:
            row = connection.execute("SELECT run_id FROM calculation_runs WHERE status='completed' ORDER BY generated_at DESC,rowid DESC LIMIT 1").fetchone()
            if row is None:
                raise LookupError("no calculation run")
            connection.execute("INSERT INTO approvals(run_id,approved,note,updated_at) VALUES(?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET approved=excluded.approved,note=excluded.note,updated_at=excluded.updated_at", (row["run_id"], int(approved), note, now))
    except LookupError:
        raise
    except sqlite3.Error as error:
        raise DatabaseError(f"Cannot persist approval: {error}") from error


def latest_recommendations(path: str | Path | None = None) -> list[dict]:
    target = initialize_database(path)
    try:
        with _connect(target) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM latest_recommendations ORDER BY supplier_name, sku"
            )]
    except sqlite3.Error as error:
        raise DatabaseError(f"Cannot export SQLite recommendations: {error}") from error
