"""Explicit paid AI integration check on temporary storage (one batch request)."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from agent import WorkflowService, OpenAIExplainer
from backend.main import create_app
from scripts.check_openai_connection import load_allowed_env


def main():
    load_allowed_env(ROOT / ".env")
    explainer = OpenAIExplainer.from_environment()
    with tempfile.TemporaryDirectory(prefix="fruktai-live-ai-") as temp:
        root = Path(temp)
        service = WorkflowService(ROOT / "data", root / "ai.sqlite", root / "runs")
        baseline = service.recalculate("demo")
        service.explainer = explainer
        with TestClient(create_app(service)) as client:
            response = client.post("/api/v1/recalculate", json={"dataset": "demo"})
            assert response.status_code == 200, "HTTP calculation failed"
            result = response.json()
            assert explainer.last_report.status == "completed", explainer.last_report.message
            assert explainer.last_report.enriched_items > 0, "No AI text generated"
            for before, after in zip(baseline["recommendations"], result["recommendations"]):
                for field, value in before.items():
                    if field != "reasons":
                        assert after[field] == value, field
                persisted = client.get("/api/v1/items/" + after["sku"]).json()
                assert persisted["calculation"]["reasons"] == after["reasons"]
        print(f"Live AI -> HTTP -> SQLite: OK ({explainer.last_report.enriched_items} items, model={explainer.model})")
        print("All deterministic business fields unchanged; temporary database removed on exit.")


if __name__ == "__main__":
    main()
