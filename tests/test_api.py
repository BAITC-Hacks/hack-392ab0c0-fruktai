from fastapi.testclient import TestClient

from backend.main import app


def _files():
    return {
        "sales_file": ("sales.csv", open("data/sales_demo.csv", "rb"), "text/csv"),
        "inventory_file": ("inventory.csv", open("data/inventory_demo.csv", "rb"), "text/csv"),
    }


def test_funnel_endpoints_and_manual_override():
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    files = _files()
    try:
        response = client.post("/api/v1/recalculate", files=files)
    finally:
        for value in files.values():
            value[1].close()
    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 6
    assert client.get("/api/v1/items/TRANSIT-001").status_code == 200
    summary = client.get("/api/v1/summary")
    assert summary.status_code == 200
    assert summary.json()["sku_count"] == 6

    files = _files()
    try:
        changed = client.post(
            "/api/v1/recalculate",
            files=files,
            data={"overrides": '{"STABLE-001":{"on_hand":9999}}'},
        )
    finally:
        for value in files.values():
            value[1].close()
    assert changed.status_code == 200
    assert client.post("/api/v1/orders/approve", json={"approved": True}).status_code == 200
    assert client.get("/api/v1/summary").json()["approved"] is True
    export = client.get("/api/v1/orders/export.csv")
    assert export.status_code == 200
    assert "recommended_qty" in export.text
