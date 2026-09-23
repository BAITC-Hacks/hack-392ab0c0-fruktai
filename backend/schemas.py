from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ContractOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1)
    on_hand: int | None = Field(default=None, ge=0, strict=True)
    in_transit: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def require_inventory_value(self):
        if any(getattr(self, key) is None for key in self.model_fields_set if key != "sku"):
            raise ValueError("Explicit null stock values are not allowed")
        if self.on_hand is None and self.in_transit is None:
            raise ValueError("on_hand or in_transit is required")
        return self


class RecalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    overrides: list[ContractOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_overrides(self):
        if len({row.sku for row in self.overrides}) != len(self.overrides):
            raise ValueError("Duplicate override SKU")
        return self


class ContractSummary(BaseModel):
    total_items: int = Field(ge=0)
    total_units_to_order: int = Field(ge=0)
    high_risk_items: int = Field(ge=0)
    anomalies_removed: int = Field(ge=0)
    estimated_stockout_items: int = Field(ge=0)


class ContractRecommendation(BaseModel):
    sku: str
    name: str
    supplier_id: str
    supplier_name: str
    recommended_qty: int = Field(ge=0)
    urgency: str
    on_hand: int = Field(ge=0)
    in_transit: int = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    avg_daily_demand: float = Field(ge=0)
    forecast_demand: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    seasonality_factor: float = Field(ge=0)
    growth_factor: float = Field(ge=0)
    stockout_compensation: float = Field(ge=0)
    outlier_units_removed: float = Field(ge=0)
    days_of_cover: float = Field(ge=0)
    reasons: list[str]


class AgentStep(BaseModel):
    step: str
    status: str
    message: str


class ContractRecalculateResponse(BaseModel):
    run_id: str
    generated_at: str
    summary: ContractSummary
    recommendations: list[ContractRecommendation]
    agent_steps: list[AgentStep]


class HistoryPoint(BaseModel):
    date: str
    units: float = Field(ge=0)
    is_outlier: bool
    is_stockout: bool
    estimated_lost_units: float = Field(ge=0)


class ItemCalculation(BaseModel):
    recommended_qty: int = Field(ge=0)
    on_hand: int = Field(ge=0)
    in_transit: int = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    avg_daily_demand: float = Field(ge=0)
    forecast_demand: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    seasonality_factor: float = Field(ge=0)
    growth_factor: float = Field(ge=0)
    stockout_compensation: float = Field(ge=0)
    outlier_units_removed: float = Field(ge=0)
    days_of_cover: float = Field(ge=0)
    reasons: list[str]


class ContractItemResponse(BaseModel):
    sku: str
    name: str
    history: list[HistoryPoint]
    calculation: ItemCalculation


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


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
