"""Offline tests for the complete OpenAI explanation funnel."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import (  # noqa: E402
    OpenAIAPIError,
    OpenAIExplainer,
    WorkflowService,
    run_workflow_with_details,
)
from scripts.test_agent_workflow import build_dataset  # noqa: E402


def structured_response(explanations: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {"explanations": explanations},
                            ensure_ascii=False,
                        ),
                    }
                ],
            }
        ],
    }


def successful_transport(requests: list[dict[str, Any]]):
    def send(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        requests.append({"payload": copy.deepcopy(payload), "timeout": timeout})
        model_input = json.loads(payload["input"])
        return structured_response(
            [
                {
                    "sku": item["sku"],
                    "explanation": (
                        "Заказ покрывает прогноз на срок поставки и страховой запас "
                        "с учётом доступного остатка и товара в пути."
                    ),
                }
                for item in model_input["recommendations"]
            ]
        )

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
            sleeper=lambda _: None,
        )
        enriched, details = explainer.enrich(
            execution.response,
            execution.item_details,
        )

        assert execution.response == original_response
        assert execution.item_details == original_details
        assert len(requests) == 1, "all SKUs must use one batch API request"
        request_payload = requests[0]["payload"]
        assert request_payload["model"] == "test-model"
        assert request_payload["store"] is False
        assert request_payload["text"]["format"]["type"] == "json_schema"
        assert request_payload["text"]["format"]["strict"] is True
        model_input = json.loads(request_payload["input"])
        assert len(model_input["recommendations"]) == len(
            enriched["recommendations"]
        )
        assert "recommended_qty" in model_input["recommendations"][0]
        assert "deterministic_reasons" in model_input["recommendations"][0]
        assert "customer_id" not in request_payload["input"]

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
        assert explainer.last_report.status == "completed"
        assert explainer.last_report.enriched_items == len(
            enriched["recommendations"]
        )
        assert explainer.last_report.attempts == 1

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key-never-sent",
                "OPENAI_MODEL": "название_доступной_модели",
                "OPENAI_MAX_RETRIES": "2",
                "OPENAI_RETRY_BASE_SECONDS": "0",
            },
            clear=False,
        ):
            assert OpenAIExplainer.from_environment().model == "gpt-6-astra"

        attempts = 0

        def transient_then_success(
            payload: dict[str, Any], timeout: float
        ) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise OpenAIAPIError("simulated rate limit", retryable=True)
            model_input = json.loads(payload["input"])
            return structured_response(
                [
                    {"sku": item["sku"], "explanation": "Проверенное пояснение."}
                    for item in model_input["recommendations"]
                ]
            )

        retrying = OpenAIExplainer(
            api_key="test-key-never-sent",
            max_retries=2,
            retry_base_seconds=0,
            transport=transient_then_success,
            sleeper=lambda _: None,
        )
        retry_response, _ = retrying.enrich(original_response, original_details)
        assert attempts == 3
        assert retrying.last_report.status == "completed"
        assert retrying.last_report.attempts == 3
        assert retry_response != original_response

        def incomplete_transport(
            payload: dict[str, Any], timeout: float
        ) -> dict[str, Any]:
            return structured_response([])

        fallback = OpenAIExplainer(
            api_key="test-key-never-sent",
            transport=incomplete_transport,
            sleeper=lambda _: None,
        )
        fallback_response, fallback_details = fallback.enrich(
            original_response,
            original_details,
        )
        assert fallback_response == original_response
        assert fallback_details == original_details
        assert fallback.last_report.status == "fallback"
        assert fallback.last_report.enriched_items == 0

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

    print("OpenAI explanation funnel offline test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
