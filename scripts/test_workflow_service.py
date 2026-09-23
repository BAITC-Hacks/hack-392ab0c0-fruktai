"""End-to-end test for the backend-facing workflow service."""

from __future__ import annotations

import math
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import (  # noqa: E402
    DataValidationError,
    DatasetNotFoundError,
    WorkflowService,
)
from database import RecordNotFoundError  # noqa: E402
from scripts.test_agent_workflow import build_dataset  # noqa: E402
from scripts.check_backend_readiness import check_backend_readiness  # noqa: E402
from scripts.validate_api_contracts import load_schemas, validate  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fruktai-service-") as temp:
        root = Path(temp)
        data_root = root / "data"
        dataset = data_root / "demo"
        database = root / "fruktai.sqlite"
        runs = root / "runs"
        dataset.mkdir(parents=True)
        build_dataset(dataset)

        service = WorkflowService(
            data_root=data_root,
            database_path=database,
            output_dir=runs,
        )
        schemas = load_schemas()

        readiness = check_backend_readiness(data_root, "demo")
        assert readiness["items"] == 1
        assert readiness["before"] > readiness["after"]

        baseline = service.recalculate("demo")
        validate(
            baseline,
            schemas["recommendation.schema.json"],
            schemas["recommendation.schema.json"],
        )
        recommendation = baseline["recommendations"][0]
        expected = max(
            0,
            recommendation["forecast_demand"]
            + recommendation["safety_stock"]
            - recommendation["on_hand"]
            - recommendation["in_transit"],
        )
        assert recommendation["recommended_qty"] == math.ceil(expected)

        detail = service.get_item("SKU-001")
        validate(
            detail,
            schemas["item.response.schema.json"],
            schemas["item.response.schema.json"],
        )
        assert len(detail["history"]) == 28
        assert sum(point["is_outlier"] for point in detail["history"]) == 1
        assert sum(point["is_stockout"] for point in detail["history"]) == 2
        assert sum(point["estimated_lost_units"] for point in detail["history"]) > 0
        assert detail["calculation"]["recommended_qty"] == recommendation["recommended_qty"]

        override = {
            "sku": "SKU-001",
            "on_hand": recommendation["on_hand"] + recommendation["recommended_qty"] + 1,
        }
        changed = service.recalculate("demo", overrides=[override])
        changed_detail = service.get_item("SKU-001")
        assert (
            changed_detail["calculation"]["recommended_qty"]
            < detail["calculation"]["recommended_qty"]
        )
        assert changed_detail["calculation"]["on_hand"] == override["on_hand"]
        assert (
            changed_detail["calculation"]["recommended_qty"]
            == changed["recommendations"][0]["recommended_qty"]
        )

        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM calculation_runs").fetchone()[0] == 2
            assert connection.execute("SELECT COUNT(*) FROM item_history").fetchone()[0] == 56
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

        try:
            service.recalculate("../demo")
        except DataValidationError:
            pass
        else:
            raise AssertionError("unsafe dataset name must fail")

        try:
            service.recalculate("missing")
        except DatasetNotFoundError:
            pass
        else:
            raise AssertionError("missing dataset must fail")

        try:
            service.get_item("UNKNOWN")
        except RecordNotFoundError:
            pass
        else:
            raise AssertionError("unknown persisted SKU must fail")

    print("workflow service integration test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
