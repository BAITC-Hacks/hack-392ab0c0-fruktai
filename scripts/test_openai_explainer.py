"""Offline tests proving that AI text cannot modify calculated values."""

from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import (  # noqa: E402
    OpenAIExplainer,
    OpenAIExplanationError,
    WorkflowService,
    run_workflow_with_details,
)
from scripts.test_agent_workflow import build_dataset  # noqa: E402


def successful_transport(
    requests: list[dict[str, Any]],
):
    def send(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        requests.append({"payload": copy.deepcopy(payload), "timeout": timeout})
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Заказ нужен для покрытия спроса на срок поставки и страхового запаса.",
                        }
                    ],
                }
            ]
        }

    return send


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fruktai-openai-") as temp:
        root = Path(temp)
        data_root = root / "data"
        dataset = data_root / "demo"
        dataset.mkdir(parents=True)
        build_dataset(dataset)

        execution = run_workflow_with_details(dataset, output_dir=root / "raw-runs")
        original_response = copy.deepcopy(execution.response)
        original_details = copy.deepcopy(execution.item_details)
        requests: list[dict[str, Any]] = []
        explainer = OpenAIExplainer(
            api_key="test-key-never-sent",
            model="test-model",
            transport=successful_transport(requests),
        )
        enriched, details = explainer.enrich(
            execution.response,
            execution.item_details,
        )

        assert execution.response == original_response
        assert execution.item_details == original_details
        assert len(requests) == len(enriched["recommendations"])
        for before, after in zip(
            original_response["recommendations"],
            enriched["recommendations"],
        ):
            for field, value in before.items():
                if field != "reasons":
                    assert after[field] == value
            assert len(after["reasons"]) == len(before["reasons"]) + 1
            assert after["reasons"][-1].startswith("AI-пояснение:")
            assert (
                details[after["sku"]]["calculation"]["reasons"][-1]
                == after["reasons"][-1]
            )
        assert requests[0]["payload"]["model"] == "test-model"
        assert "recommended_qty" in requests[0]["payload"]["input"]

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key-never-sent",
                "OPENAI_MODEL": "название_доступной_модели",
            },
            clear=False,
        ):
            assert OpenAIExplainer.from_environment().model == "gpt-6-astra"

        def failing_transport(
            payload: dict[str, Any], timeout: float
        ) -> dict[str, Any]:
            raise OpenAIExplanationError("simulated timeout")

        fallback = OpenAIExplainer(
            api_key="test-key-never-sent",
            transport=failing_transport,
        )
        fallback_response, fallback_details = fallback.enrich(
            original_response,
            original_details,
        )
        assert fallback_response == original_response
        assert fallback_details == original_details

        service = WorkflowService(
            data_root=data_root,
            database_path=root / "fruktai.sqlite",
            output_dir=root / "service-runs",
            explainer=explainer,
        )
        result = service.recalculate("demo")
        item = service.get_item("SKU-001")
        assert result["recommendations"][0]["reasons"][-1].startswith(
            "AI-пояснение:"
        )
        assert item["calculation"]["reasons"][-1].startswith("AI-пояснение:")

    print("OpenAI explainer offline test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
