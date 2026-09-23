from __future__ import annotations

import csv
import json
from io import StringIO
import os
from datetime import date
from pathlib import Path
from math import ceil

import pandas as pd
from fastapi import FastAPI, HTTPException

from .ai_explainer import OpenAIExplainer, explanations_enabled
from .calculation import calculate_recommendations
from .schemas import ApprovalRequest, ApprovalResponse, ContractItemResponse, ContractRecalculateResponse, HealthResponse, RecalculateRequest, SummaryResponse
from database import DatabaseError, initialize_database, latest_item_detail, latest_summary, latest_recommendations, persist_run, set_approval

app = FastAPI(title="Supplier Replenishment API", version="1.0.0")
_latest: dict[str, object] = {}
_approved = False
_ai_explainer: OpenAIExplainer | None = None


@app.on_event("startup")
def initialize_storage() -> None:
    global _ai_explainer
    initialize_database()
    _ai_explainer = (
        OpenAIExplainer.from_environment() if explanations_enabled() else None
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


def _read_dataset(dataset: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not dataset or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in dataset):
        raise ValueError("dataset may contain only Latin letters, digits, '_' and '-'")
    root = Path(os.getenv("FRUKTAI_DATA_ROOT", "data")).resolve()
    folder = (root / dataset).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("dataset path escapes the configured data root")
    if not folder.is_dir():
        raise FileNotFoundError(f"Dataset not found: {dataset}")

    requirements = {
        "products": {"sku", "name", "supplier_id", "active"},
        "suppliers": {"supplier_id", "supplier_name", "lead_time_days"},
        "sales": {"date", "sku", "units"},
        "inventory": {"sku", "on_hand"},
        "in_transit": {"sku", "quantity", "expected_date"},
        "stockouts": {"sku", "start_date", "end_date"},
    }
    source: dict[str, pd.DataFrame] = {}
    for name, columns in requirements.items():
        path = folder / f"{name}.csv"
        if not path.is_file():
            raise ValueError(f"Required dataset file not found: {path.name}")
        frame = pd.read_csv(path)
        missing = columns - set(frame.columns)
        if missing:
            raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
        source[name] = frame

    for frame in source.values():
        if "sku" in frame:
            frame["sku"] = frame["sku"].astype(str).str.strip().str.upper()
    products, suppliers = source["products"], source["suppliers"]
    if products.sku.duplicated().any() or suppliers.supplier_id.duplicated().any():
        raise ValueError("products.sku and suppliers.supplier_id must be unique")
    products["active"] = products["active"].map(lambda value: str(value).strip().lower() in {"1", "true", "yes"})
    active_products = products.loc[products.active].copy()
    active_skus = set(active_products.sku)
    if source["inventory"].sku.duplicated().any():
        raise ValueError("inventory.csv must contain one row per SKU")
    if active_skus - set(source["inventory"].sku):
        raise ValueError("every active product must have an inventory row")
    for name in ("sales", "in_transit", "stockouts"):
        unknown = set(source[name].sku) - set(products.sku)
        if unknown:
            raise ValueError(f"{name}.csv contains unknown SKUs: {sorted(unknown)}")
        # Inactive products are deliberately absent from this run's inventory and
        # recommendation set, so exclude their historical rows from persistence too.
        source[name] = source[name].loc[source[name].sku.isin(active_skus)].copy()
    inventory = source["inventory"].merge(active_products, on="sku", how="inner").merge(suppliers, on="supplier_id", how="left")
    if inventory["supplier_name"].isna().any():
        raise ValueError("products reference a missing supplier")
    inventory = inventory.rename(columns={"supplier_name": "supplier"})
    inventory["lead_time_days"] = pd.to_numeric(inventory["lead_time_days"], errors="raise")

    sales = source["sales"].rename(columns={"units": "quantity"}).copy()
    sales["customer_id"] = "anonymized-unavailable"
    sales["stockout"] = False
    sales["date"] = pd.to_datetime(sales["date"], errors="raise").dt.normalize()
    stockout_rows = []
    for row in source["stockouts"].itertuples(index=False):
        start, end = pd.Timestamp(row.start_date).normalize(), pd.Timestamp(row.end_date).normalize()
        if end < start:
            raise ValueError("stockout end_date is before start_date")
        # Sales recorded during an explicitly declared stockout are censored
        # observations, not evidence of normal demand.
        affected = (sales.sku == row.sku) & sales.date.between(start, end)
        sales.loc[affected, "stockout"] = True
        observed_stockout_dates = set(sales.loc[affected, "date"])
        for day in pd.date_range(start, end, freq="D"):
            if day not in observed_stockout_dates:
                stockout_rows.append({"date": day, "sku": row.sku, "quantity": 0.0, "customer_id": "anonymized-unavailable", "stockout": True})
    if stockout_rows:
        sales = pd.concat([sales, pd.DataFrame(stockout_rows)], ignore_index=True)

    transit = source["in_transit"].copy()
    transit["expected_date"] = pd.to_datetime(transit["expected_date"], errors="raise").dt.normalize()
    as_of = sales["date"].max() if not sales.empty else pd.Timestamp(date.today())
    as_of = min(as_of, pd.Timestamp(date.today()))
    sales = sales.loc[sales.date <= as_of].copy()
    inventory["in_transit"] = 0.0
    inventory["eta"] = pd.NaT
    for idx, product in inventory.iterrows():
        shipments = transit.loc[transit.sku == product.sku]
        eligible = shipments.loc[shipments.expected_date <= as_of + pd.Timedelta(days=int(product.lead_time_days))]
        inventory.loc[idx, "in_transit"] = pd.to_numeric(eligible.quantity, errors="raise").sum()
        if not eligible.empty:
            inventory.loc[idx, "eta"] = eligible.expected_date.min()
    return sales, inventory, transit


@app.post("/api/v1/recalculate", response_model=ContractRecalculateResponse)
def recalculate(request: RecalculateRequest) -> ContractRecalculateResponse:
    global _approved
    try:
        sales, inventory, transit = _read_dataset(request.dataset)
        source_inventory = inventory.copy(deep=True)
        override_map = {}
        for override in request.overrides:
            sku = override.sku.strip().upper()
            if sku in override_map:
                raise ValueError(f"duplicate override for SKU {sku}")
            match = inventory.sku == sku
            if not match.any():
                raise ValueError(f"override references unknown SKU: {sku}")
            override_map[sku] = override.model_dump(exclude_none=True, exclude={"sku"})
            if override.on_hand is not None:
                inventory.loc[match, "on_hand"] = override.on_hand
            if override.in_transit is not None:
                inventory.loc[match, "in_transit"] = override.in_transit

        calculation_date = sales["date"].max()
        if pd.isna(calculation_date):
            calculation_date = pd.Timestamp(date.today())
        internal = calculate_recommendations(sales, inventory, as_of_date=calculation_date.date().isoformat())
        recommendation_dicts = []
        for item in internal.recommendations:
            product = inventory.loc[inventory.sku == item.sku].iloc[0]
            qty = int(ceil(item.recommended_qty))
            reasons = [f"{reason.text}: {reason.value:.2f}" if reason.value is not None else reason.text for reason in item.reasons]
            recommendation_dicts.append({
                "sku": item.sku, "name": item.name or item.sku,
                "supplier_id": str(product.supplier_id), "supplier_name": item.supplier,
                "recommended_qty": qty, "urgency": item.urgency,
                "on_hand": int(item.on_hand), "in_transit": int(item.in_transit),
                "lead_time_days": item.lead_time_days,
                "avg_daily_demand": round(item.normal_daily_demand, 2),
                "forecast_demand": round(item.forecast_demand_during_lead_time, 2),
                "safety_stock": round(item.safety_stock, 2),
                "seasonality_factor": round(item.coefficients["seasonality"], 2),
                "growth_factor": round(max(0.0, 1.0 + item.coefficients["growth"]), 2),
                "stockout_compensation": round(item.lost_demand, 2),
                "outlier_units_removed": round(item.excluded_units, 2),
                "days_of_cover": round(item.days_of_cover, 2), "reasons": reasons,
            })
        response = {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat().replace("+00:00", "Z"),
            "summary": {
                "total_items": len(recommendation_dicts),
                "total_units_to_order": sum(item["recommended_qty"] for item in recommendation_dicts),
                "high_risk_items": sum(item["urgency"] == "high" for item in recommendation_dicts),
                "anomalies_removed": sum(item["outlier_units_removed"] > 0 for item in recommendation_dicts),
                "estimated_stockout_items": sum(item["stockout_compensation"] > 0 for item in recommendation_dicts),
            },
            "recommendations": recommendation_dicts,
            "agent_steps": [
                {"step": step, "status": "completed", "message": message}
                for step, message in [
                    ("load_data", f"Loaded dataset {request.dataset}"),
                    ("validate_data", "Validated source tables, SKUs, dates, and overrides"),
                    ("detect_outliers", "Marked one-off demand observations for robust calculation"),
                    ("estimate_lost_demand", "Compensated explicitly listed stockout dates"),
                    ("calculate_recommendations", "Calculated per-SKU order recommendations"),
                    ("validate_result", "Validated non-negative integer order quantities"),
                    ("save_result", "Persisted source snapshot and calculation to SQLite"),
                ]
            ],
        }
        if _ai_explainer is not None:
            response, _ = _ai_explainer.enrich(response)
        run_id = persist_run(sales, source_inventory, response, override_map, transit, dataset=request.dataset)
        response["run_id"] = run_id
        # Public calculations and all drill-down data now survive process restarts.
        _latest.clear()
        _latest.update({item["sku"]: item for item in recommendation_dicts})
        _approved = False
        return ContractRecalculateResponse(**response)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, pd.errors.ParserError, DatabaseError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/items/{sku}", response_model=ContractItemResponse)
def get_item(sku: str) -> ContractItemResponse:
    try:
        return ContractItemResponse(**latest_item_detail(sku))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="SKU not found in the latest database run") from exc
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    try:
        values = latest_summary()
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not values:
        raise HTTPException(status_code=404, detail="run recalculation first")
    return SummaryResponse(**values)


@app.post("/api/v1/orders/approve", response_model=ApprovalResponse)
def approve_orders(request: ApprovalRequest) -> ApprovalResponse:
    """Record explicit human approval in the current process; never sends an order."""
    global _approved
    try:
        current = latest_summary()
        if not current:
            raise HTTPException(status_code=404, detail="run recalculation first")
        set_approval(request.approved, request.note)
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    _approved = request.approved
    if not request.approved:
        return ApprovalResponse(status="rejected", approved=False, item_count=int(current["sku_count"]), total_recommended_qty=round(float(current["total_recommended_qty"]), 4))
    return ApprovalResponse(status="approved", approved=True, item_count=int(current["sku_count"]), total_recommended_qty=round(float(current["total_recommended_qty"]), 4))


@app.get("/api/v1/orders/export.csv")
def export_orders() -> object:
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["sku", "supplier", "recommended_qty", "urgency", "inventory_position", "reorder_point"])
    try:
        rows = latest_recommendations()
    except DatabaseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    for row in rows:
        calculation = json.loads(row["calculation_json"])
        inventory_position = calculation["on_hand"] + calculation["in_transit"]
        reorder_point = calculation["forecast_demand"] + calculation["safety_stock"]
        writer.writerow([row["sku"], row["supplier_name"], row["recommended_qty"], row["urgency"], inventory_position, reorder_point])
    from fastapi.responses import Response
    return Response(content=stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=supplier-orders.csv"})
