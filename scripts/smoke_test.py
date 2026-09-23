"""HTTP smoke test for an integrated FruktAI backend.

Usage:

    python scripts/smoke_test.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent.api_client import BackendAPIError, get_item, health, recalculate  # noqa: E402


RESPONSE_FIELDS = {"run_id", "generated_at", "summary", "recommendations", "agent_steps"}
SUMMARY_FIELDS = {
    "total_items",
    "total_units_to_order",
    "high_risk_items",
    "anomalies_removed",
    "estimated_stockout_items",
}
RECOMMENDATION_FIELDS = {
    "sku",
    "name",
    "supplier_id",
    "supplier_name",
    "recommended_qty",
    "urgency",
    "on_hand",
    "in_transit",
    "lead_time_days",
    "avg_daily_demand",
    "forecast_demand",
    "safety_stock",
    "seasonality_factor",
    "growth_factor",
    "stockout_compensation",
    "outlier_units_removed",
    "days_of_cover",
    "reasons",
}
STEP_FIELDS = {"step", "status", "message"}
EXPECTED_STEPS = [
    "load_data",
    "validate_data",
    "detect_outliers",
    "estimate_lost_demand",
    "calculate_recommendations",
    "validate_result",
    "save_result",
]


def require_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError(f"{label} must be a JSON object")
    missing = fields - value.keys()
    if missing:
        raise AssertionError(f"{label} is missing: {', '.join(sorted(missing))}")
    return value


def validate_response(response: dict[str, Any]) -> None:
    require_fields(response, RESPONSE_FIELDS, "recalculate response")
    require_fields(response["summary"], SUMMARY_FIELDS, "summary")
    if not isinstance(response["recommendations"], list):
        raise AssertionError("recommendations must be an array")
    if not isinstance(response["agent_steps"], list):
        raise AssertionError("agent_steps must be an array")
    for index, recommendation in enumerate(response["recommendations"]):
        item = require_fields(recommendation, RECOMMENDATION_FIELDS, f"recommendations[{index}]")
        if item["urgency"] not in {"high", "medium", "low"}:
            raise AssertionError(f"invalid urgency for {item['sku']}")
        if not isinstance(item["recommended_qty"], int) or item["recommended_qty"] < 0:
            raise AssertionError(f"invalid recommended_qty for {item['sku']}")
        for field in (
            "avg_daily_demand",
            "forecast_demand",
            "safety_stock",
            "seasonality_factor",
            "growth_factor",
            "stockout_compensation",
            "outlier_units_removed",
            "days_of_cover",
        ):
            value = item[field]
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise AssertionError(f"invalid {field} for {item['sku']}")
    steps = []
    for index, entry in enumerate(response["agent_steps"]):
        step = require_fields(entry, STEP_FIELDS, f"agent_steps[{index}]")
        steps.append(step["step"])
    if steps != EXPECTED_STEPS:
        raise AssertionError(f"unexpected workflow order: {steps}")


def run(base_url: str, dataset: str) -> None:
    health_response = health(base_url)
    if health_response != {"status": "ok"}:
        raise AssertionError(f"unexpected /health response: {health_response}")

    baseline = recalculate(base_url, dataset=dataset)
    validate_response(baseline)
    orderable = next(
        (item for item in baseline["recommendations"] if item["recommended_qty"] > 0),
        None,
    )
    if orderable is None:
        raise AssertionError("demo dataset must contain at least one SKU with recommended_qty > 0")

    replacement_on_hand = orderable["on_hand"] + orderable["recommended_qty"] + 1
    changed = recalculate(
        base_url,
        dataset=dataset,
        overrides=[{"sku": orderable["sku"], "on_hand": replacement_on_hand}],
    )
    validate_response(changed)
    changed_item = next(
        item for item in changed["recommendations"] if item["sku"] == orderable["sku"]
    )
    if changed_item["recommended_qty"] >= orderable["recommended_qty"]:
        raise AssertionError(
            f"on_hand override did not lower recommended_qty for {orderable['sku']}"
        )

    detail = get_item(base_url, orderable["sku"])
    require_fields(detail, {"sku", "name", "history", "calculation"}, "item detail")
    if detail["sku"] != orderable["sku"]:
        raise AssertionError("item detail returned a different SKU")
    if not isinstance(detail["history"], list):
        raise AssertionError("item detail history must be an array")
    require_fields(
        detail["calculation"],
        {
            "recommended_qty",
            "on_hand",
            "in_transit",
            "lead_time_days",
            "avg_daily_demand",
            "forecast_demand",
            "safety_stock",
            "seasonality_factor",
            "growth_factor",
            "stockout_compensation",
            "outlier_units_removed",
            "days_of_cover",
            "reasons",
        },
        "item calculation",
    )

    print(
        "smoke test: OK "
        f"({orderable['sku']} recommended_qty "
        f"{orderable['recommended_qty']} -> {changed_item['recommended_qty']})"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--dataset", default="demo")
    arguments = parser.parse_args()
    try:
        run(arguments.base_url, arguments.dataset)
    except (AssertionError, BackendAPIError, KeyError, StopIteration) as error:
        print(f"smoke test: FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
