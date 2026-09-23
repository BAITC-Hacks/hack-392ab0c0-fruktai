"""Optional OpenAI explanation layer for deterministic recommendations.

The model output is accepted only as plain explanatory text appended to
``reasons``. It is never parsed as a quantity and cannot replace calculation
fields produced by the deterministic orchestrator.
"""

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
    """Raised when an optional explanation cannot be generated or parsed."""


class OpenAIExplainer:
    """Generate bounded Russian explanations without changing calculations."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 20.0,
        max_items: int = 20,
        transport: Transport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when explanations are enabled")
        if not model or not model.strip():
            raise ValueError("OPENAI_MODEL must be a non-empty model ID")
        if timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS must be positive")
        if max_items < 0:
            raise ValueError("OPENAI_MAX_EXPLANATION_ITEMS must be non-negative")
        self._api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.max_items = max_items
        self._transport = transport or self._request

    @classmethod
    def from_environment(cls) -> "OpenAIExplainer":
        try:
            timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
            max_items = int(os.getenv("OPENAI_MAX_EXPLANATION_ITEMS", "20"))
        except ValueError as error:
            raise ValueError(
                "OPENAI_TIMEOUT_SECONDS and OPENAI_MAX_EXPLANATION_ITEMS "
                "must be numeric"
            ) from error
        configured_model = os.getenv("OPENAI_MODEL", "").strip()
        if configured_model.lower() in {
            "",
            "your_model_here",
            "model_id_here",
            "название_доступной_модели",
        }:
            configured_model = DEFAULT_MODEL
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=configured_model,
            timeout_seconds=timeout,
            max_items=max_items,
        )

    def enrich(
        self,
        response: dict[str, Any],
        item_details: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Append model text while preserving every deterministic value."""

        enriched_response = copy.deepcopy(response)
        enriched_details = copy.deepcopy(item_details)
        original_by_sku = {
            item["sku"]: copy.deepcopy(item)
            for item in response.get("recommendations", [])
        }

        for item in enriched_response.get("recommendations", [])[: self.max_items]:
            try:
                explanation = self.explain(item)
            except OpenAIExplanationError as error:
                # LLM text is optional. Stop further paid calls for this run and
                # preserve the complete deterministic response.
                LOGGER.warning("OpenAI explanation fallback: %s", error)
                break
            reason = f"AI-пояснение: {explanation}"
            item["reasons"].append(reason)
            detail = enriched_details.get(item["sku"])
            if detail is not None:
                detail["calculation"]["reasons"].append(reason)

        self._assert_calculation_unchanged(original_by_sku, enriched_response)
        return enriched_response, enriched_details

    def explain(self, recommendation: dict[str, Any]) -> str:
        facts = {
            "sku": recommendation["sku"],
            "name": recommendation["name"],
            "recommended_qty": recommendation["recommended_qty"],
            "urgency": recommendation["urgency"],
            "on_hand": recommendation["on_hand"],
            "in_transit": recommendation["in_transit"],
            "lead_time_days": recommendation["lead_time_days"],
            "avg_daily_demand": recommendation["avg_daily_demand"],
            "forecast_demand": recommendation["forecast_demand"],
            "safety_stock": recommendation["safety_stock"],
            "seasonality_factor": recommendation["seasonality_factor"],
            "growth_factor": recommendation["growth_factor"],
            "stockout_compensation": recommendation["stockout_compensation"],
            "outlier_units_removed": recommendation["outlier_units_removed"],
            "days_of_cover": recommendation["days_of_cover"],
            "deterministic_reasons": recommendation["reasons"],
        }
        payload = {
            "model": self.model,
            "instructions": (
                "Ты объясняешь уже рассчитанную рекомендацию по закупке. "
                "Не пересчитывай, не меняй и не предлагай другое количество. "
                "Используй только переданные факты. Верни одно понятное предложение "
                "на русском языке без Markdown, JSON и вводных фраз, максимум 45 слов."
            ),
            "input": json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
            "max_output_tokens": 160,
        }
        raw = self._transport(payload, self.timeout_seconds)
        text = self._extract_output_text(raw)
        normalized = " ".join(text.split())
        if not normalized:
            raise OpenAIExplanationError("model returned empty text")
        # Bound untrusted external text before it reaches the API response/DB.
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
            with urlopen(request, timeout=timeout) as response:
                value = json.load(response)
        except HTTPError as error:
            raise OpenAIExplanationError(
                f"Responses API returned HTTP {error.code}"
            ) from error
        except URLError as error:
            raise OpenAIExplanationError(
                f"Responses API is unavailable: {error.reason}"
            ) from error
        except (OSError, TimeoutError) as error:
            raise OpenAIExplanationError("Responses API request timed out") from error
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
        for output in response.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        return text
        raise OpenAIExplanationError("Responses API payload has no output text")

    @staticmethod
    def _assert_calculation_unchanged(
        original_by_sku: dict[str, dict[str, Any]],
        enriched_response: dict[str, Any],
    ) -> None:
        for item in enriched_response.get("recommendations", []):
            original = original_by_sku.get(item.get("sku"))
            if original is None:
                raise OpenAIExplanationError("explanation layer added an unknown SKU")
            for field, original_value in original.items():
                if field == "reasons":
                    continue
                if item.get(field) != original_value:
                    raise OpenAIExplanationError(
                        f"explanation layer changed protected field {field}"
                    )


def explanations_enabled() -> bool:
    value = os.getenv("OPENAI_EXPLANATIONS_ENABLED", "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("OPENAI_EXPLANATIONS_ENABLED must be true or false")


__all__ = [
    "DEFAULT_MODEL",
    "OpenAIExplainer",
    "OpenAIExplanationError",
    "explanations_enabled",
]
