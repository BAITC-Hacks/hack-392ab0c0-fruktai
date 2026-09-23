"""Optional OpenAI text explanations; recommendation math remains deterministic."""

from __future__ import annotations

import copy
import json
import logging
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)
RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-6-astra"
Transport = Callable[[dict[str, Any], float], dict[str, Any]]


class OpenAIExplanationError(RuntimeError):
    """An optional explanation could not be fetched or safely parsed."""


class OpenAIExplainer:
    """Append bounded Russian text without accepting model-generated quantities."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 20.0,
        max_items: int = 20,
        transport: Transport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when explanations are enabled")
        if not model.strip():
            raise ValueError("OPENAI_MODEL must be non-empty")
        if timeout_seconds <= 0 or max_items < 0:
            raise ValueError("OpenAI timeout must be positive and item limit non-negative")
        self._api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.max_items = max_items
        self._transport = transport or self._request

    @classmethod
    def from_environment(cls) -> OpenAIExplainer:
        try:
            timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
            max_items = int(os.getenv("OPENAI_MAX_EXPLANATION_ITEMS", "20"))
        except ValueError as error:
            raise ValueError("OpenAI timeout and item limit must be numeric") from error
        model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=model,
            timeout_seconds=timeout,
            max_items=max_items,
        )

    def enrich(
        self,
        response: dict[str, Any],
        item_details: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        enriched = copy.deepcopy(response)
        details = copy.deepcopy(item_details or {})
        original = {
            item["sku"]: copy.deepcopy(item)
            for item in response.get("recommendations", [])
        }
        for item in enriched.get("recommendations", [])[: self.max_items]:
            try:
                explanation = self.explain(item)
            except OpenAIExplanationError as error:
                LOGGER.warning("OpenAI explanation fallback: %s", error)
                break
            reason = f"AI-пояснение: {explanation}"
            item["reasons"].append(reason)
            detail = details.get(item["sku"])
            if detail is not None:
                detail["calculation"]["reasons"].append(reason)
        self._assert_calculation_unchanged(original, enriched)
        return enriched, details

    def explain(self, item: dict[str, Any]) -> str:
        fields = (
            "sku", "name", "recommended_qty", "urgency", "on_hand", "in_transit",
            "lead_time_days", "avg_daily_demand", "forecast_demand", "safety_stock",
            "seasonality_factor", "growth_factor", "stockout_compensation",
            "outlier_units_removed", "days_of_cover", "reasons",
        )
        facts = {field: item[field] for field in fields if field in item}
        payload = {
            "model": self.model,
            "instructions": (
                "Объясни готовую рекомендацию по закупке одним коротким предложением на русском. "
                "Используй только переданные факты. Не пересчитывай и не меняй количество. "
                "Не возвращай JSON или Markdown; максимум 45 слов."
            ),
            "input": json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
            "max_output_tokens": 160,
        }
        try:
            raw = self._transport(payload, self.timeout_seconds)
        except OpenAIExplanationError:
            raise
        except Exception as error:
            raise OpenAIExplanationError("Responses API request failed") from error
        if not isinstance(raw, dict):
            raise OpenAIExplanationError("Responses API returned a non-object payload")
        text = self._extract_output_text(raw)
        normalized = " ".join(text.split())
        if not normalized:
            raise OpenAIExplanationError("model returned empty text")
        return normalized[:500]

    def _request(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        request = Request(
            RESPONSES_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as result:
                value = json.load(result)
        except HTTPError as error:
            raise OpenAIExplanationError(
                f"Responses API returned HTTP {error.code}"
            ) from error
        except (URLError, OSError, TimeoutError) as error:
            raise OpenAIExplanationError("Responses API is unavailable or timed out") from error
        except json.JSONDecodeError as error:
            raise OpenAIExplanationError("Responses API returned invalid JSON") from error
        if not isinstance(value, dict):
            raise OpenAIExplanationError("Responses API returned a non-object payload")
        return value

    @staticmethod
    def _extract_output_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        outputs = response.get("output", [])
        if not isinstance(outputs, list):
            raise OpenAIExplanationError("Responses API payload has invalid output")
        for output in outputs:
            if not isinstance(output, dict):
                continue
            contents = output.get("content", [])
            if not isinstance(contents, list):
                continue
            for content in contents:
                if (
                    isinstance(content, dict)
                    and content.get("type") in {"output_text", "text"}
                    and isinstance(content.get("text"), str)
                ):
                    return content["text"]
        raise OpenAIExplanationError("Responses API payload has no output text")

    @staticmethod
    def _assert_calculation_unchanged(
        original: dict[str, dict[str, Any]], enriched: dict[str, Any]
    ) -> None:
        for item in enriched.get("recommendations", []):
            source = original.get(item.get("sku"))
            if source is None:
                raise OpenAIExplanationError("explanation added an unknown SKU")
            for field, value in source.items():
                if field != "reasons" and item.get(field) != value:
                    raise OpenAIExplanationError(
                        f"explanation changed protected field {field}"
                    )


def explanations_enabled() -> bool:
    value = os.getenv("OPENAI_EXPLANATIONS_ENABLED", "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPENAI_EXPLANATIONS_ENABLED must be true or false")
