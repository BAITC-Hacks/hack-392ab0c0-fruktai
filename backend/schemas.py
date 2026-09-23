from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Reason(BaseModel):
    code: str
    text: str
    value: float | None = None


class Recommendation(BaseModel):
    sku: str
    name: str | None = None
    supplier: str
    category: str | None = None
    recommended_qty: float = Field(ge=0)
    urgency: str
    on_hand: float = Field(ge=0)
    in_transit: float = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    normal_daily_demand: float = Field(ge=0)
    stockout_days: float = Field(ge=0)
    lost_demand: float = Field(ge=0)
    forecast_demand_during_lead_time: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    coefficients: dict[str, float]
    excluded_units: float = Field(ge=0)
    reasons: list[Reason]


class SupplierOrder(BaseModel):
    supplier: str
    total_recommended_qty: float = Field(ge=0)
    items: list[Recommendation]


class RecalculateResponse(BaseModel):
    as_of_date: str
    recommendations: list[Recommendation]
    by_supplier: list[SupplierOrder]
    warnings: list[str] = []


class HealthResponse(BaseModel):
    status: str
    service: str


class RecalculateOptions(BaseModel):
    as_of_date: str | None = None
    safety_z: float = Field(default=1.65, ge=0, le=4)


class ItemResponse(BaseModel):
    recommendation: Recommendation
