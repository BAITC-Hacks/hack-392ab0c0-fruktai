from fastapi.testclient import TestClient

from backend.main import app


def test_contract_api_is_backed_by_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("FRUKTAI_DATABASE_PATH", str(tmp_path / "api.sqlite"))
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    calculated = client.post("/api/v1/recalculate", json={"dataset": "demo"})
    assert calculated.status_code == 200
    body = calculated.json()
    assert set(body) == {"run_id", "generated_at", "summary", "recommendations", "agent_steps"}
    assert body["summary"]["total_items"] == 6
    assert body["recommendations"][0]["supplier_id"]

    sku = body["recommendations"][0]["sku"]
    detail = client.get(f"/api/v1/items/{sku}")
    assert detail.status_code == 200
    assert detail.json()["sku"] == sku
    assert "calculation" in detail.json()

    recalculated = client.post(
        "/api/v1/recalculate",
        json={"dataset": "demo", "overrides": [{"sku": sku, "on_hand": 10000}]},
    )
    assert recalculated.status_code == 200
    changed = next(item for item in recalculated.json()["recommendations"] if item["sku"] == sku)
    assert changed["recommended_qty"] <= next(item for item in body["recommendations"] if item["sku"] == sku)["recommended_qty"]

    assert client.get("/api/v1/summary").status_code == 200
    assert client.post("/api/v1/orders/approve", json={"approved": True}).status_code == 200
    export = client.get("/api/v1/orders/export.csv")
    assert export.status_code == 200
    assert "recommended_qty" in export.text


def test_unknown_dataset_and_bad_override_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("FRUKTAI_DATABASE_PATH", str(tmp_path / "api.sqlite"))
    client = TestClient(app)
    assert client.post("/api/v1/recalculate", json={"dataset": "missing"}).status_code == 404
    invalid = client.post("/api/v1/recalculate", json={"dataset": "demo", "unexpected": True})
    assert invalid.status_code == 422
