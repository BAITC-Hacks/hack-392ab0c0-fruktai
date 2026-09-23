"""Validated OpenAI explanation stage for deterministic recommendations.

The language model receives only aggregate, already calculated facts. Its
strictly structured output can append human-readable text to ``reasons`` but
cannot replace quantities, urgency, suppliers, or any calculation field.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from .openai_client import (
    OpenAIAPIError,
    OpenAIResponsesClient,
    Sleeper,
    Transport,
)


from .explanation_contract import (
    DEFAULT_MODEL,
    AI_REASON_PREFIX,
    INSTRUCTIONS,
    OpenAIExplanationError,
    _build_facts,
    _extract_output_text,
    _parse_output,
    _assert_protected_data_unchanged,
    _structured_output_schema,
)

LOGGER = logging.getLogger(__name__)


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
            _assert_protected_data_unchanged(
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
        model_input = {"recommendations": [_build_facts(item) for item in recommendations]}
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
            raw_text = _extract_output_text(result.payload)
            parsed = _parse_output(raw_text, model_input)
        except OpenAIExplanationError as error:
            error.attempts = result.attempts
            raise
        return parsed, result.attempts

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
