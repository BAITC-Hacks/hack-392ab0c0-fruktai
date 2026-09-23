from fastapi.testclient import TestClient

from backend import main
from backend.ai_explainer import OpenAIExplainer, OpenAIExplanationError


def recommendation():
    return {
        "sku": "SKU-AI-1",
        "name": "Test item",
        "supplier_id": "SUP-1",
        "supplier_name": "Test supplier",
        "recommended_qty": 17,
        "urgency": "high",
        "on_hand": 4,
        "in_transit": 2,
        "lead_time_days": 5,
        "avg_daily_demand": 2.0,
        "forecast_demand": 10.0,
        "safety_stock": 3.0,
        "seasonality_factor": 1.0,
        "growth_factor": 1.0,
        "stockout_compensation": 0.0,
        "outlier_units_removed": 0.0,
        "days_of_cover": 3.0,
        "reasons": ["Объяснение расчёта: прогноз + страховой запас - доступный остаток"],
    }


def test_explanation_changes_only_reason_text():
    calls = []

    def fake_transport(payload, timeout):
        calls.append((payload, timeout))
        return {"output_text": "Запас ниже потребности на срок поставки."}

    source = recommendation()
    result = {"summary": {"total_units_to_order": 17}, "recommendations": [source]}
    enriched, _ = OpenAIExplainer("not-a-real-key", transport=fake_transport).enrich(result)

    actual = enriched["recommendations"][0]
    assert actual["recommended_qty"] == source["recommended_qty"]
    assert {key: value for key, value in actual.items() if key != "reasons"} == {
        key: value for key, value in source.items() if key != "reasons"
    }
    assert actual["reasons"][-1].startswith("AI-пояснение:")
    assert len(calls) == 1
    assert "recommended_qty" in calls[0][0]["input"]


def test_model_failure_falls_back_to_deterministic_reasons():
    def failed_transport(payload, timeout):
        raise OpenAIExplanationError("simulated API failure")

    source = recommendation()
    enriched, _ = OpenAIExplainer("not-a-real-key", transport=failed_transport).enrich(
        {"recommendations": [source]}
    )
    assert enriched["recommendations"][0] == source


def test_malformed_model_response_falls_back_to_deterministic_reasons():
    source = recommendation()
    enriched, _ = OpenAIExplainer(
        "not-a-real-key", transport=lambda payload, timeout: {"output": None}
    ).enrich({"recommendations": [source]})
    assert enriched["recommendations"][0] == source


def test_api_ai_explanation_is_persisted_without_changing_order(tmp_path, monkeypatch):
    monkeypatch.setenv("FRUKTAI_DATABASE_PATH", str(tmp_path / "ai-pipeline.sqlite"))
    monkeypatch.setenv("OPENAI_EXPLANATIONS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
    explainer = OpenAIExplainer(
        "test-key-never-sent",
        transport=lambda payload, timeout: {
            "output_text": "Проверка stockout и сезонности завершена." 
        },
    )
    monkeypatch.setattr(
        main.OpenAIExplainer,
        "from_environment",
        classmethod(lambda cls: explainer),
    )

    with TestClient(main.app) as client:
        response = client.post("/api/v1/recalculate", json={"dataset": "demo"})
        assert response.status_code == 200, response.text
        item = response.json()["recommendations"][0]
        assert item["recommended_qty"] >= 0
        assert any(reason.startswith("AI-пояснение:") for reason in item["reasons"])

        detail = client.get(f"/api/v1/items/{item['sku']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["calculation"]["recommended_qty"] == item["recommended_qty"]
        assert any(
            reason.startswith("AI-пояснение:")
            for reason in detail.json()["calculation"]["reasons"]
        )
