"""Immutable AI input/output boundary, schema loading and merge guards."""

import copy
import json
import math
from pathlib import Path
from typing import Any
from .openai_client import OpenAIAPIError

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
            raise OpenAIExplanationError(f"AI input field {field} must be a non-negative integer")
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


def _build_facts(recommendation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(recommendation, dict):
        raise OpenAIExplanationError("recommendation must be an object")
    missing = [field for field in FACT_FIELDS if field not in recommendation]
    if "reasons" not in recommendation:
        missing.append("reasons")
    if missing:
        raise OpenAIExplanationError(f"recommendation is missing fields: {', '.join(missing)}")

    facts = {field: recommendation[field] for field in FACT_FIELDS}
    facts["deterministic_reasons"] = copy.deepcopy(recommendation["reasons"])
    _validate_facts(facts)
    return facts


def _extract_output_text(response: dict[str, Any]) -> str:
    if response.get("error"):
        raise OpenAIExplanationError("Responses API returned an error object")
    status = response.get("status")
    if status not in {None, "completed"}:
        raise OpenAIExplanationError(f"Responses API did not complete (status={status})")
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

    expected_skus = [item["sku"] for item in model_input.get("recommendations", [])]
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


def _assert_protected_data_unchanged(
    original_response: dict[str, Any],
    enriched_response: dict[str, Any],
    original_details: dict[str, dict[str, Any]],
    enriched_details: dict[str, dict[str, Any]],
) -> None:
    for field, value in original_response.items():
        if field != "recommendations" and enriched_response.get(field) != value:
            raise OpenAIExplanationError(f"AI stage changed protected response field {field}")
    before_items = original_response.get("recommendations", [])
    after_items = enriched_response.get("recommendations", [])
    if len(before_items) != len(after_items):
        raise OpenAIExplanationError("AI stage changed recommendation count")
    for before, after in zip(before_items, after_items):
        for field, value in before.items():
            if field != "reasons" and after.get(field) != value:
                raise OpenAIExplanationError(f"AI stage changed protected field {field}")

    if set(original_details) != set(enriched_details):
        raise OpenAIExplanationError("AI stage changed item-detail SKU set")
    for sku, before in original_details.items():
        after = enriched_details[sku]
        for field, value in before.items():
            if field != "calculation" and after.get(field) != value:
                raise OpenAIExplanationError(f"AI stage changed protected item field {field}")
        before_calculation = before.get("calculation", {})
        after_calculation = after.get("calculation", {})
        for field, value in before_calculation.items():
            if field != "reasons" and after_calculation.get(field) != value:
                raise OpenAIExplanationError(
                    f"AI stage changed protected calculation field {field}"
                )
