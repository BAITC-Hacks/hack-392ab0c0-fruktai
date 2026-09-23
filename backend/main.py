from __future__ import annotations

from io import BytesIO
import csv
import json
from io import StringIO

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .calculation import calculate_recommendations
from .schemas import ApprovalRequest, ApprovalResponse, HealthResponse, ItemResponse, RecalculateResponse, SummaryResponse

app = FastAPI(title="Supplier Replenishment API", version="1.0.0")
_latest: dict[str, object] = {}
_approved = False


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="supplier-replenishment")


@app.post("/api/v1/recalculate", response_model=RecalculateResponse)
async def recalculate(
    sales_file: UploadFile = File(...),
    inventory_file: UploadFile = File(...),
    as_of_date: str | None = Form(default=None),
    safety_z: float = Form(default=1.65),
    overrides: str | None = Form(default=None),
) -> RecalculateResponse:
    global _approved
    try:
        sales = pd.read_csv(BytesIO(await sales_file.read()))
        inventory = pd.read_csv(BytesIO(await inventory_file.read()))
        if sales.empty or inventory.empty:
            raise ValueError("sales and inventory CSV files must not be empty")
        if overrides:
            override_map = json.loads(overrides)
            if not isinstance(override_map, dict):
                raise ValueError("overrides must be a JSON object keyed by SKU")
            inventory = inventory.copy()
            for sku, values in override_map.items():
                match = inventory.sku.astype(str).str.strip().str.upper() == str(sku).strip().upper()
                if not match.any() or not isinstance(values, dict):
                    continue
                for field in ("on_hand", "in_transit", "backorders", "reserved"):
                    if field in values:
                        inventory.loc[match, field] = values[field]
        result = calculate_recommendations(sales, inventory, as_of_date=as_of_date, safety_z=safety_z)
        if "eta" not in inventory.columns and (pd.to_numeric(inventory.get("in_transit", 0), errors="coerce").fillna(0) > 0).any():
            result.warnings.append("ETA отсутствует: товары в пути считаются доступными в protection period")
        if "customer_id" not in sales.columns:
            result.warnings.append("customer_id отсутствует: проверка крупных продаж одному клиенту ограничена")
        if len(sales.date.unique()) < 14:
            result.warnings.append("История короче 14 дней: используется fallback baseline без подтверждения недельной сезонности")
    except (ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _latest.clear()
    _latest.update({item.sku: item for item in result.recommendations})
    _approved = False
    return result


@app.get("/api/v1/items/{sku}", response_model=ItemResponse)
def get_item(sku: str) -> ItemResponse:
    item = _latest.get(sku.strip().upper())
    if item is None:
        raise HTTPException(status_code=404, detail="SKU not found; run recalculation first")
    return ItemResponse(recommendation=item)


@app.get("/api/v1/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    if not _latest:
        raise HTTPException(status_code=404, detail="run recalculation first")
    items = list(_latest.values())
    return SummaryResponse(
        sku_count=len(items),
        items_to_order=sum(item.recommended_qty > 0 for item in items),
        high_urgency_count=sum(item.urgency == "high" for item in items),
        medium_urgency_count=sum(item.urgency == "medium" for item in items),
        low_urgency_count=sum(item.urgency == "low" for item in items),
        total_recommended_qty=round(sum(item.recommended_qty for item in items), 4),
        supplier_count=len({item.supplier for item in items}),
        excluded_outlier_units=round(sum(item.excluded_units for item in items), 4),
        stockout_items=sum(item.stockout_days > 0 for item in items),
        approved=_approved,
    )


@app.post("/api/v1/orders/approve", response_model=ApprovalResponse)
def approve_orders(request: ApprovalRequest) -> ApprovalResponse:
    """Record explicit human approval in the current process; never sends an order."""
    global _approved
    items = list(_latest.values())
    if not items:
        raise HTTPException(status_code=404, detail="run recalculation first")
    _approved = request.approved
    if not request.approved:
        return ApprovalResponse(status="rejected", approved=False, item_count=len(items), total_recommended_qty=round(sum(i.recommended_qty for i in items), 4))
    return ApprovalResponse(status="approved", approved=True, item_count=len(items), total_recommended_qty=round(sum(i.recommended_qty for i in items), 4))


@app.get("/api/v1/orders/export.csv")
def export_orders() -> object:
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["sku", "supplier", "recommended_qty", "urgency", "inventory_position", "reorder_point"])
    for item in sorted(_latest.values(), key=lambda x: (x.supplier, x.sku)):
        writer.writerow([item.sku, item.supplier, item.recommended_qty, item.urgency, item.inventory_position, item.reorder_point])
    from fastapi.responses import Response
    return Response(content=stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=supplier-orders.csv"})
