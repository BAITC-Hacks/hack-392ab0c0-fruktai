"""Exercise the real HTTP adapter, workflow and SQLite on isolated storage."""

import math
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent import WorkflowService, OpenAIExplainer, OpenAIAPIError
from backend.main import create_app
from scripts.validate_api_contracts import load_schemas, validate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def service(tmp_path):
    return WorkflowService(ROOT / "data", tmp_path / "test.sqlite", tmp_path / "runs")


def test_http_database_restart_and_overrides(service):
    schemas = load_schemas()
    with TestClient(create_app(service)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/v1/items/missing").status_code == 404
        response = client.post("/api/v1/recalculate", json={"dataset": "demo"})
        assert response.status_code == 200, response.text
        result = response.json()
        validate(
            result, schemas["recommendation.schema.json"], schemas["recommendation.schema.json"]
        )
        assert len(result["recommendations"]) == 6
        item = next(r for r in result["recommendations"] if r["recommended_qty"] > 20)
        for row in result["recommendations"]:
            assert row["recommended_qty"] == math.ceil(
                max(
                    0,
                    row["forecast_demand"]
                    + row["safety_stock"]
                    - row["on_hand"]
                    - row["in_transit"],
                )
            )
        for field in ("on_hand", "in_transit"):
            updated = client.post(
                "/api/v1/recalculate",
                json={
                    "dataset": "demo",
                    "overrides": [{"sku": item["sku"], field: item[field] + 10}],
                },
            ).json()
            changed = next(r for r in updated["recommendations"] if r["sku"] == item["sku"])
            assert changed["recommended_qty"] == item["recommended_qty"] - 10
            detail = client.get("/api/v1/items/" + item["sku"]).json()
            validate(
                detail, schemas["item.response.schema.json"], schemas["item.response.schema.json"]
            )
            assert detail["calculation"][field] == changed[field]
            assert detail["history"]
    # New app AND service instance must read the saved data after a restart.
    restarted = WorkflowService(service.data_root, service.database_path, service.output_dir)
    with TestClient(create_app(restarted)) as client:
        assert client.get("/api/v1/items/" + item["sku"]).json() == detail
    with sqlite3.connect(service.database_path) as db:
        assert db.execute("SELECT count(*) FROM calculation_runs").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM item_history").fetchone()[0] > 0


@pytest.mark.parametrize(
    "payload",
    [
        {"dataset": "../demo"},
        {"dataset": "demo", "surprise": 1},
        {"dataset": "demo", "overrides": [{"sku": "STABLE-001"}]},
        {"dataset": "demo", "overrides": [{"sku": "STABLE-001", "on_hand": -1}]},
        {"dataset": "demo", "overrides": [{"sku": "STABLE-001", "on_hand": 1.5}]},
        {"dataset": "demo", "overrides": [{"sku": "STABLE-001", "on_hand": True}]},
        {"dataset": "demo", "overrides": [{"sku": "STABLE-001", "on_hand": None, "in_transit": 5}]},
        {"dataset": "demo", "overrides": [{"sku": "UNKNOWN", "on_hand": 5}]},
        {"dataset": "demo", "overrides": [{"sku": "STABLE-001", "on_hand": 5}] * 2},
    ],
)
def test_bad_request_is_422(service, payload):
    with TestClient(create_app(service)) as client:
        assert client.post("/api/v1/recalculate", json=payload).status_code == 422


def test_missing_dataset_is_404(service):
    with TestClient(create_app(service)) as client:
        assert client.post("/api/v1/recalculate", json={"dataset": "missing"}).status_code == 404


def test_ai_outage_preserves_http_result(service):
    def unavailable(payload, timeout):
        raise OpenAIAPIError("simulated unavailable", retryable=False)

    service.explainer = OpenAIExplainer("test-key", transport=unavailable)
    with TestClient(create_app(service)) as client:
        result = client.post("/api/v1/recalculate", json={"dataset": "demo"})
        assert result.status_code == 200
        assert service.explainer.last_report.status == "fallback"
        assert result.json()["summary"]["total_units_to_order"] > 0
