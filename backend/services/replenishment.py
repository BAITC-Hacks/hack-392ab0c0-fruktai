from __future__ import annotations

import math


def calculate_inventory_position(
    on_hand: float,
    in_transit: float = 0.0,
    backorders: float = 0.0,
    reserved: float = 0.0,
    eligible_in_transit: float | None = None,
) -> float:
    transit = in_transit if eligible_in_transit is None else eligible_in_transit
    return max(0.0, on_hand - reserved) + max(0.0, transit) - max(0.0, backorders)


def calculate_safety_stock(
    service_level: float,
    forecast_error_std: float,
    protection_period: float,
    z: float | None = None,
) -> float:
    if z is None:
        z = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}.get(
            round(service_level, 3), 1.6449
        )
    return max(
        0.0, float(z) * max(0.0, forecast_error_std) * math.sqrt(max(0.0, protection_period))
    )


def calculate_order_quantity(
    forecast_demand: float,
    safety_stock: float,
    inventory_position: float,
    pack_size: float = 1,
    moq: float = 0,
    max_stock: float | None = None,
) -> dict[str, float]:
    target_stock = max(0.0, forecast_demand) + max(0.0, safety_stock)
    raw = max(0.0, target_stock - inventory_position)
    pack = max(1.0, pack_size)
    rounded = math.ceil(raw / pack) * pack if raw else 0.0
    moq_qty = max(rounded, moq) if raw > 0 else 0.0
    final = (
        min(moq_qty, max(0.0, max_stock - inventory_position)) if max_stock is not None else moq_qty
    )
    return {
        "target_stock": target_stock,
        "raw_order_qty": raw,
        "recommended_qty": max(0.0, final),
        "pack_size": pack,
        "minimum_order_qty": max(0.0, moq),
    }


def calculate_reorder_point(
    forecast_lead_time: float, safety_stock: float, inventory_position: float
) -> dict[str, float | bool]:
    point = max(0.0, forecast_lead_time) + max(0.0, safety_stock)
    return {
        "reorder_point": point,
        "inventory_position": inventory_position,
        "reorder_triggered": inventory_position <= point,
    }
