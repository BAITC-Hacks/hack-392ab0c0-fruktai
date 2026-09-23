"""Validated OpenAI explanation stage for deterministic recommendations.

The language model receives only aggregate, already calculated facts. Its
strictly structured output can append human-readable text to ``reasons`` but
cannot replace quantities, urgency, suppliers, or any calculation field.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .openai_client import (
    OpenAIAPIError,
    OpenAIResponsesClient,
    Sleeper,
    Transport,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "gpt-6-astra"
AI_REASON_PREFIX = "AI-пояснение: "
MAX_EXPLANATION_CHARACTERS = 500
CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"

FACT_FIELDS = (
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
)
INTEGER_FIELDS = {
    "recommended_qty",
    "on_hand",
    "in_transit",
    "lead_time_days",
}
NUMBER_FIELDS = {
    "avg_daily_demand",
    "forecast_demand",
    "safety_stock",
    "seasonality_factor",
    "growth_factor",
    "stockout_compensation",
    "outlier_units_removed",
    "days_of_cover",
}
TEXT_FIELDS = {"sku", "name", "supplier_id", "supplier_name"}

INSTRUCTIONS = """Ты объясняешь менеджеру закупок уже рассчитанные рекомендации FruktAI.
Для каждого переданного SKU верни ровно одно краткое объяснение на русском языке.
Объясни рекомендуемое количество через срок поставки, прогноз спроса, страховой
запас, остаток и товар в пути. Упомяни сезонность, рост, компенсацию stockout или
удалённый выброс только когда соответствующий фактор реально значим.
Не пересчитывай и не меняй числа, срочность, SKU или поставщика. Не предлагай
другое количество и не добавляй фактов, которых нет во входе. Не упоминай
клиентов и персональные данные. Не используй Markdown. Каждое объяснение должно
быть самостоятельным, понятным и не длиннее двух предложений.
Верни только JSON, соответствующий переданной строгой схеме."""


class OpenAIExplanationError(OpenAIAPIError):
    """Raised when model output cannot safely enrich recommendations."""


@dataclass(frozen=True)
class AIEnrichmentReport:
    """Internal audit summary; it is not part of the public HTTP contract."""

    status: str
    model: str
    requested_items: int
    enriched_items: int
    attempts: int
    message: str


class OpenAIExplainer:
    """Run the complete AI input -> API -> validation -> merge funnel."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 20.0,
        max_items: int = 20,
        max_retries: int = 2,
        retry_base_seconds: float = 0.5,
        transport: Transport | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        if not model or not model.strip():
            raise ValueError("OPENAI_MODEL must be a non-empty model ID")
        if max_items < 0:
            raise ValueError("OPENAI_MAX_EXPLANATION_ITEMS must be non-negative")
        self.model = model.strip()
        self.max_items = max_items
        client_options: dict[str, Any] = {
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "retry_base_seconds": retry_base_seconds,
            "transport": transport,
        }
        if sleeper is not None:
            client_options["sleeper"] = sleeper
        self._client = OpenAIResponsesClient(api_key, **client_options)
        self.last_report = AIEnrichmentReport(
            status="skipped",
            model=self.model,
            requested_items=0,
            enriched_items=0,
            attempts=0,
            message="AI stage has not run yet",
        )

    @classmethod
    def from_environment(cls) -> "OpenAIExplainer":
        """Build a strictly validated explainer from backend environment."""

        configured_model = os.getenv("OPENAI_MODEL", "").strip()
        if configured_model.lower() in {
            "",
            "your_model_here",
            "model_id_here",
            "название_доступной_модели",
        }:
            configured_model = DEFAULT_MODEL
        try:
            timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
            max_items = int(os.getenv("OPENAI_MAX_EXPLANATION_ITEMS", "20"))
            max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
            retry_base = float(os.getenv("OPENAI_RETRY_BASE_SECONDS", "0.5"))
        except ValueError as error:
            raise ValueError(
                "OpenAI timeout, item limit, retries, and retry delay must be numeric"
            ) from error
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=configured_model,
            timeout_seconds=timeout,
            max_items=max_items,
            max_retries=max_retries,
            retry_base_seconds=retry_base,
        )

    def enrich(
        self,
        response: dict[str, Any],
        item_details: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Atomically append verified explanations or return input unchanged."""

        original_response = copy.deepcopy(response)
        original_details = copy.deepcopy(item_details)
        recommendations = response.get("recommendations")
        if not isinstance(recommendations, list):
            return self._fallback(
                original_response,
                original_details,
                requested_items=0,
                error=OpenAIExplanationError("recommendations must be an array"),
            )
        selected = recommendations[: self.max_items]
        if not selected:
            self.last_report = AIEnrichmentReport(
                status="skipped",
                model=self.model,
                requested_items=0,
                enriched_items=0,
                attempts=0,
                message="No recommendations selected for AI explanation",
            )
            return original_response, original_details

        try:
            explanations, attempts = self._explain_many(selected)
            enriched_response = copy.deepcopy(original_response)
            enriched_details = copy.deepcopy(original_details)
            for item in enriched_response["recommendations"][: len(selected)]:
                sku = item["sku"]
                reason = f"{AI_REASON_PREFIX}{explanations[sku]}"
                item["reasons"].append(reason)
                detail = enriched_details.get(sku)
                if detail is not None:
                    detail["calculation"]["reasons"].append(reason)
            self._assert_protected_data_unchanged(
                original_response,
                enriched_response,
                original_details,
                enriched_details,
            )
        except OpenAIAPIError as error:
            return self._fallback(
                original_response,
                original_details,
                requested_items=len(selected),
                error=error,
            )
        except (KeyError, TypeError, AttributeError):
            return self._fallback(
                original_response,
                original_details,
                requested_items=len(selected),
                error=OpenAIExplanationError(
                    "AI merge boundary rejected malformed deterministic data"
                ),
            )

        self.last_report = AIEnrichmentReport(
            status="completed",
            model=self.model,
            requested_items=len(selected),
            enriched_items=len(selected),
            attempts=attempts,
            message="Structured AI explanations validated and merged",
        )
        LOGGER.info(
            "OpenAI explanation stage completed: model=%s items=%d attempts=%d",
            self.model,
            len(selected),
            attempts,
        )
        return enriched_response, enriched_details

    def explain(self, recommendation: dict[str, Any]) -> str:
        """Explain one item; used by the explicit connection-check script."""

        explanations, _ = self._explain_many([recommendation])
        sku = recommendation.get("sku")
        if not isinstance(sku, str):
            raise OpenAIExplanationError("recommendation has no valid SKU")
        return explanations[sku]

    def _explain_many(
        self,
        recommendations: list[dict[str, Any]],
    ) -> tuple[dict[str, str], int]:
        model_input = {
            "recommendations": [self._build_facts(item) for item in recommendations]
        }
        payload = {
            "model": self.model,
            "instructions": INSTRUCTIONS,
            "input": json.dumps(
                model_input,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "fruktai_explanations",
                    "strict": True,
                    "schema": _structured_output_schema(),
                }
            },
            "max_output_tokens": max(256, min(8192, len(recommendations) * 180)),
            "store": False,
        }
        result = self._client.create(payload)
        try:
            raw_text = self._extract_output_text(result.payload)
            parsed = self._parse_output(raw_text, model_input)
        except OpenAIExplanationError as error:
            error.attempts = result.attempts
            raise
        return parsed, result.attempts

    @staticmethod
    def _build_facts(recommendation: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(recommendation, dict):
            raise OpenAIExplanationError("recommendation must be an object")
        missing = [field for field in FACT_FIELDS if field not in recommendation]
        if "reasons" not in recommendation:
            missing.append("reasons")
        if missing:
            raise OpenAIExplanationError(
                f"recommendation is missing fields: {', '.join(missing)}"
            )

        facts = {field: recommendation[field] for field in FACT_FIELDS}
        facts["deterministic_reasons"] = copy.deepcopy(recommendation["reasons"])
        _validate_facts(facts)
        return facts

    @staticmethod
    def _extract_output_text(response: dict[str, Any]) -> str:
        if response.get("error"):
            raise OpenAIExplanationError("Responses API returned an error object")
        status = response.get("status")
        if status not in {None, "completed"}:
            raise OpenAIExplanationError(
                f"Responses API did not complete (status={status})"
            )
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        for output in response.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal":
                    raise OpenAIExplanationError("Model refused the explanation request")
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        return text
        raise OpenAIExplanationError("Responses API payload has no output text")

    @staticmethod
    def _parse_output(
        raw_text: str,
        model_input: dict[str, Any],
    ) -> dict[str, str]:
        try:
            value = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise OpenAIExplanationError("Model output is not valid JSON") from error
        if not isinstance(value, dict) or set(value) != {"explanations"}:
            raise OpenAIExplanationError("Model output has unexpected top-level fields")
        explanations = value["explanations"]
        if not isinstance(explanations, list):
            raise OpenAIExplanationError("Model explanations must be an array")

        expected_skus = [
            item["sku"] for item in model_input.get("recommendations", [])
        ]
        parsed: dict[str, str] = {}
        for item in explanations:
            if not isinstance(item, dict) or set(item) != {"sku", "explanation"}:
                raise OpenAIExplanationError("Model explanation item has invalid fields")
            sku = item.get("sku")
            explanation = item.get("explanation")
            if not isinstance(sku, str) or sku not in expected_skus:
                raise OpenAIExplanationError("Model returned an unknown SKU")
            if sku in parsed:
                raise OpenAIExplanationError("Model returned a duplicate SKU")
            if not isinstance(explanation, str):
                raise OpenAIExplanationError("Model explanation must be text")
            normalized = " ".join(explanation.split())
            if not normalized:
                raise OpenAIExplanationError("Model returned an empty explanation")
            if len(normalized) > MAX_EXPLANATION_CHARACTERS:
                raise OpenAIExplanationError("Model explanation exceeds the safe limit")
            parsed[sku] = normalized
        if set(parsed) != set(expected_skus) or len(parsed) != len(expected_skus):
            raise OpenAIExplanationError(
                "Model output does not contain exactly one explanation per SKU"
            )
        return parsed

    def _fallback(
        self,
        response: dict[str, Any],
        details: dict[str, dict[str, Any]],
        *,
        requested_items: int,
        error: OpenAIAPIError,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        attempts = getattr(error, "attempts", 0)
        self.last_report = AIEnrichmentReport(
            status="fallback",
            model=self.model,
            requested_items=requested_items,
            enriched_items=0,
            attempts=attempts,
            message=str(error),
        )
        LOGGER.warning(
            "OpenAI explanation fallback: model=%s items=%d attempts=%d reason=%s",
            self.model,
            requested_items,
            attempts,
            error,
        )
        return response, details

    @staticmethod
    def _assert_protected_data_unchanged(
        original_response: dict[str, Any],
        enriched_response: dict[str, Any],
        original_details: dict[str, dict[str, Any]],
        enriched_details: dict[str, dict[str, Any]],
    ) -> None:
        for field, value in original_response.items():
            if field != "recommendations" and enriched_response.get(field) != value:
                raise OpenAIExplanationError(
                    f"AI stage changed protected response field {field}"
                )
        before_items = original_response.get("recommendations", [])
        after_items = enriched_response.get("recommendations", [])
        if len(before_items) != len(after_items):
            raise OpenAIExplanationError("AI stage changed recommendation count")
        for before, after in zip(before_items, after_items):
            for field, value in before.items():
                if field != "reasons" and after.get(field) != value:
                    raise OpenAIExplanationError(
                        f"AI stage changed protected field {field}"
                    )

        if set(original_details) != set(enriched_details):
            raise OpenAIExplanationError("AI stage changed item-detail SKU set")
        for sku, before in original_details.items():
            after = enriched_details[sku]
            for field, value in before.items():
                if field != "calculation" and after.get(field) != value:
                    raise OpenAIExplanationError(
                        f"AI stage changed protected item field {field}"
                    )
            before_calculation = before.get("calculation", {})
            after_calculation = after.get("calculation", {})
            for field, value in before_calculation.items():
                if field != "reasons" and after_calculation.get(field) != value:
                    raise OpenAIExplanationError(
                        f"AI stage changed protected calculation field {field}"
                    )


def _validate_facts(facts: dict[str, Any]) -> None:
    for field in TEXT_FIELDS:
        value = facts.get(field)
        if not isinstance(value, str) or not value.strip():
            raise OpenAIExplanationError(f"AI input field {field} must be text")
    if facts.get("urgency") not in {"high", "medium", "low"}:
        raise OpenAIExplanationError("AI input urgency is invalid")
    for field in INTEGER_FIELDS:
        value = facts.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise OpenAIExplanationError(
                f"AI input field {field} must be a non-negative integer"
            )
    for field in NUMBER_FIELDS:
        value = facts.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise OpenAIExplanationError(
                f"AI input field {field} must be a finite non-negative number"
            )
    reasons = facts.get("deterministic_reasons")
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) or not reason.strip() for reason in reasons
    ):
        raise OpenAIExplanationError(
            "AI input deterministic_reasons must be an array of non-empty strings"
        )


def _structured_output_schema() -> dict[str, Any]:
    path = CONTRACTS_DIR / "ai-explanation.output.schema.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OpenAIExplanationError("AI output schema cannot be loaded") from error
    return {
        key: copy.deepcopy(contract[key])
        for key in ("type", "additionalProperties", "required", "properties")
    }


def explanations_enabled() -> bool:
    value = os.getenv("OPENAI_EXPLANATIONS_ENABLED", "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPENAI_EXPLANATIONS_ENABLED must be true or false")


__all__ = [
    "AIEnrichmentReport",
    "AI_REASON_PREFIX",
    "DEFAULT_MODEL",
    "OpenAIExplainer",
    "OpenAIExplanationError",
    "explanations_enabled",
]
