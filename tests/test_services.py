import numpy as np
import pandas as pd
import pytest

from backend.services.data_processing import (
    build_daily_demand_series,
    detect_transaction_outliers,
    estimate_lost_demand,
)
from backend.services.forecasting import median_baseline, rolling_origin_backtest
from backend.services.replenishment import (
    calculate_inventory_position,
    calculate_order_quantity,
    calculate_safety_stock,
)


def test_manual_control_example():
    safety = calculate_safety_stock(0.95, 4, 10, z=1.6449)
    order = calculate_order_quantity(
        100, round(safety), calculate_inventory_position(40, 30, 5), 12, 48
    )
    assert safety == pytest.approx(20.809, abs=0.01)
    assert order["target_stock"] == 121
    assert order["raw_order_qty"] == 56
    assert order["recommended_qty"] == 60


def test_daily_layer_and_stockout_use_only_previous_history():
    sales = pd.DataFrame(
        [
            {"date": "2026-01-01", "sku": "A", "quantity": 10},
            {"date": "2026-01-08", "sku": "A", "quantity": 12},
            {"date": "2026-01-15", "sku": "A", "quantity": 0},
        ]
    )
    stockouts = pd.DataFrame([{"sku": "A", "date": "2026-01-15"}])
    daily = build_daily_demand_series(sales, stockouts=stockouts)
    corrected = estimate_lost_demand(daily)
    row = corrected.loc[corrected.date == pd.Timestamp("2026-01-15")].iloc[0]
    assert row.is_stockout
    assert row.estimated_lost_demand == 11
    assert row.corrected_demand == 11


def test_outlier_detection_is_per_sku_and_repeated_large_sales_remain():
    rows = [
        {"date": f"2026-01-{i:02d}", "sku": "A", "quantity": 100, "customer_id": "c1"}
        for i in range(1, 5)
    ]
    rows += [
        {"date": f"2026-01-{i:02d}", "sku": "B", "quantity": 10, "customer_id": "c2"}
        for i in range(1, 5)
    ]
    rows += [{"date": "2026-01-05", "sku": "B", "quantity": 1000, "customer_id": "c2"}]
    annotated, summary = detect_transaction_outliers(pd.DataFrame(rows))
    assert not annotated.loc[annotated.sku == "A", "is_outlier"].any()
    assert summary.loc[summary.sku == "B", "is_outlier"].any()


def test_pack_moq_and_non_negative():
    order = calculate_order_quantity(5, 0, 100, pack_size=12, moq=48)
    assert order["recommended_qty"] == 0
    order = calculate_order_quantity(100, 0, 0, pack_size=12, moq=48)
    assert order["recommended_qty"] % 12 == 0
    assert order["recommended_qty"] >= 48


def test_backtest_selects_baseline_when_complex_model_is_worse():
    series = pd.Series(np.ones(60) * 10)
    bad = lambda s, h: np.repeat(100.0, h)
    result = rolling_origin_backtest(
        series, [("median_baseline", median_baseline), ("bad", bad)], horizon=7
    )
    assert result.selected_model == "median_baseline"
