"""Check whether real demo data is ready for backend integration.

This command never writes to the configured production database. It runs the
full service against a temporary SQLite file and validates both API responses.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import WorkflowService  # noqa: E402
from scripts.validate_api_contracts import load_schemas, validate  # noqa: E402


REQUIRED_FILES = (
    "sales.csv",
    "inventory.csv",
    "stockouts.csv",
    "suppliers.csv",
    "in_transit.csv",
    "products.csv",
)


def check_backend_readiness(data_root: Path, dataset: str) -> dict[str, Any]:
    dataset_path = data_root / dataset
    missing = [name for name in REQUIRED_FILES if not (dataset_path / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"{dataset_path} is missing required files: {', '.join(missing)}"
        )

    schemas = load_schemas()
    with tempfile.TemporaryDirectory(prefix="fruktai-readiness-") as temp:
        workspace = Path(temp)
        service = WorkflowService(
            data_root=data_root,
            database_path=workspace / "readiness.sqlite",
            output_dir=workspace / "runs",
        )
        response = service.recalculate(dataset)
        validate(
            response,
            schemas["recommendation.schema.json"],
            schemas["recommendation.schema.json"],
        )
        if not response["recommendations"]:
            raise AssertionError("dataset produced no active recommendations")
        orderable = next(
            (
                item
                for item in response["recommendations"]
                if item["recommended_qty"] > 0
            ),
            None,
        )
        if orderable is None:
            raise AssertionError(
                "demo dataset needs at least one positive recommendation for smoke test"
            )
        item = service.get_item(orderable["sku"])
        validate(
            item,
            schemas["item.response.schema.json"],
            schemas["item.response.schema.json"],
        )
        changed = service.recalculate(
            dataset,
            overrides=[
                {
                    "sku": orderable["sku"],
                    "on_hand": orderable["on_hand"]
                    + orderable["recommended_qty"]
                    + 1,
                }
            ],
        )
        changed_item = next(
            value
            for value in changed["recommendations"]
            if value["sku"] == orderable["sku"]
        )
        if changed_item["recommended_qty"] >= orderable["recommended_qty"]:
            raise AssertionError("on_hand override did not lower recommended_qty")
        return {
            "dataset": dataset,
            "items": response["summary"]["total_items"],
            "units_to_order": response["summary"]["total_units_to_order"],
            "override_sku": orderable["sku"],
            "before": orderable["recommended_qty"],
            "after": changed_item["recommended_qty"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--dataset", default="demo")
    arguments = parser.parse_args()
    try:
        result = check_backend_readiness(arguments.data_root, arguments.dataset)
    except (AssertionError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"backend readiness: FAILED: {error}", file=sys.stderr)
        return 1
    print(
        "backend readiness: OK "
        f"({result['items']} items, {result['units_to_order']} units, "
        f"{result['override_sku']} {result['before']} -> {result['after']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

