from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .calculation import calculate_recommendations
from .schemas import HealthResponse, ItemResponse, RecalculateResponse

app = FastAPI(title="Supplier Replenishment API", version="1.0.0")
_latest: dict[str, object] = {}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="supplier-replenishment")


@app.post("/api/v1/recalculate", response_model=RecalculateResponse)
async def recalculate(
    sales_file: UploadFile = File(...),
    inventory_file: UploadFile = File(...),
    as_of_date: str | None = Form(default=None),
    safety_z: float = Form(default=1.65),
) -> RecalculateResponse:
    try:
        sales = pd.read_csv(BytesIO(await sales_file.read()))
        inventory = pd.read_csv(BytesIO(await inventory_file.read()))
        result = calculate_recommendations(sales, inventory, as_of_date=as_of_date, safety_z=safety_z)
    except (ValueError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _latest.clear()
    _latest.update({item.sku: item for item in result.recommendations})
    return result


@app.get("/api/v1/items/{sku}", response_model=ItemResponse)
def get_item(sku: str) -> ItemResponse:
    item = _latest.get(sku.strip().upper())
    if item is None:
        raise HTTPException(status_code=404, detail="SKU not found; run recalculation first")
    return ItemResponse(recommendation=item)
