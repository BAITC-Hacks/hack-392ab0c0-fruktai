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
    forecast_model: str = "median_baseline"
    review_period_days: int = Field(default=0, ge=0)
    protection_period_days: int = Field(default=0, ge=0)
    reorder_point: float = Field(default=0, ge=0)
    # Inventory position may be negative when backorders exceed available stock.
    inventory_position: float = 0
    target_stock: float = Field(default=0, ge=0)
    raw_order_qty: float = Field(default=0, ge=0)
    pack_size: float = Field(default=1, ge=0)
    minimum_order_qty: float = Field(default=0, ge=0)
    service_level: float = Field(default=0.95, gt=0, le=1)
    days_of_cover: float = Field(default=0, ge=0)
    reorder_triggered: bool = False


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


class ApprovalRequest(BaseModel):
    approved: bool
    note: str | None = None


class ApprovalResponse(BaseModel):
    status: str
    approved: bool
    item_count: int
    total_recommended_qty: float


class SummaryResponse(BaseModel):
    sku_count: int = Field(ge=0)
    items_to_order: int = Field(ge=0)
    high_urgency_count: int = Field(ge=0)
    medium_urgency_count: int = Field(ge=0)
    low_urgency_count: int = Field(ge=0)
    total_recommended_qty: float = Field(ge=0)
    supplier_count: int = Field(ge=0)
    excluded_outlier_units: float = Field(ge=0)
    stockout_items: int = Field(ge=0)
    approved: bool = False
