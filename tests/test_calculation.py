import pandas as pd

from backend.calculation import calculate_recommendations


def frames():
    sales = pd.DataFrame([
        {"date": f"2026-01-{i:02d}", "sku": "A", "quantity": 10, "customer_id": "c1", "stockout": False}
        for i in range(1, 21)
    ])
    inventory = pd.DataFrame([{"sku": "A", "supplier": "S", "on_hand": 0, "in_transit": 0, "lead_time_days": 5}])
    return sales, inventory


def one(sales, inventory):
    return calculate_recommendations(sales, inventory).recommendations[0]


def test_on_hand_and_transit_reduce_order():
    sales, inventory = frames()
    base = one(sales, inventory).recommended_qty
    inventory.loc[0, "on_hand"] = 10
    assert one(sales, inventory).recommended_qty < base
    inventory.loc[0, "on_hand"] = 0
    inventory.loc[0, "in_transit"] = 10
    assert one(sales, inventory).recommended_qty < base


def test_stockout_increases_corrected_demand():
    sales, inventory = frames()
    raw = one(sales, inventory)
    sales.loc[0:2, "stockout"] = True
    corrected = one(sales, inventory)
    assert corrected.lost_demand > 0
    assert corrected.forecast_demand_during_lead_time > raw.forecast_demand_during_lead_time


def test_single_large_customer_order_does_not_destroy_forecast():
    sales, inventory = frames()
    normal = one(sales, inventory)
    sales.loc[len(sales)] = ["2026-01-21", "A", 1000, "big-client", False]
    outlier = one(sales, inventory)
    assert outlier.excluded_units > 0
    assert outlier.normal_daily_demand < 100
    assert outlier.recommended_qty < normal.recommended_qty * 3


def test_seasonality_coefficient_is_visible_and_bounded():
    sales, inventory = frames()
    sales = pd.concat([sales, pd.DataFrame([
        {"date": f"2026-02-{i:02d}", "sku": "A", "quantity": 20, "customer_id": "c1", "stockout": False}
        for i in range(1, 21)
    ])], ignore_index=True)
    result = one(sales, inventory)
    assert 1.0 < result.coefficients["seasonality"] <= 2.0


def test_recommended_qty_is_never_negative():
    sales, inventory = frames()
    inventory.loc[0, "on_hand"] = 9999
    inventory.loc[0, "in_transit"] = 9999
    assert one(sales, inventory).recommended_qty == 0
