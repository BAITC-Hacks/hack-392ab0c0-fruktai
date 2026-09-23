"""Small, dependency-free client for the OpenAI Responses API.

The client owns HTTP, authentication, timeout handling, and bounded retries.
Domain prompts and response validation live in ``openai_explainer.py``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from email.message import Message
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RESPONSES_URL = "https://api.openai.com/v1/responses"
RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 429})
Transport = Callable[[dict[str, Any], float], dict[str, Any]]
Sleeper = Callable[[float], None]


class OpenAIAPIError(RuntimeError):
    """Safe API error that never contains credentials or response bodies."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        attempts: int = 0,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.attempts = attempts


@dataclass(frozen=True)
class OpenAIResponseResult:
    """Validated transport result and number of HTTP attempts used."""

    payload: dict[str, Any]
    attempts: int


class OpenAIResponsesClient:
    """Call ``POST /v1/responses`` with finite exponential backoff."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        retry_base_seconds: float = 0.5,
        transport: Transport | None = None,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required when explanations are enabled")
        if timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_SECONDS must be positive")
        if max_retries < 0:
            raise ValueError("OPENAI_MAX_RETRIES must be non-negative")
        if retry_base_seconds < 0:
            raise ValueError("OPENAI_RETRY_BASE_SECONDS must be non-negative")
        self._api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self._transport = transport or self._request_once
        self._sleeper = sleeper

    def create(self, payload: dict[str, Any]) -> OpenAIResponseResult:
        """Create one response, retrying only transient failures."""

        attempts = 0
        while True:
            attempts += 1
            try:
                value = self._transport(payload, self.timeout_seconds)
                if not isinstance(value, dict):
                    raise OpenAIAPIError(
                        "Responses API returned a non-object payload",
                        attempts=attempts,
                    )
                return OpenAIResponseResult(payload=value, attempts=attempts)
            except OpenAIAPIError as error:
                error.attempts = attempts
                if not error.retryable or attempts > self.max_retries:
                    raise
                delay = error.retry_after_seconds
                if delay is None:
                    delay = self.retry_base_seconds * (2 ** (attempts - 1))
                self._sleeper(min(max(delay, 0.0), 8.0))

    def _request_once(
        self,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
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
            status = int(error.code)
            raise OpenAIAPIError(
                f"Responses API returned HTTP {status}",
                status_code=status,
                retryable=status in RETRYABLE_HTTP_STATUSES or status >= 500,
                retry_after_seconds=_retry_after_seconds(error.headers),
            ) from error
        except URLError as error:
            raise OpenAIAPIError(
                "Responses API is unavailable",
                retryable=True,
            ) from error
        except (OSError, TimeoutError) as error:
            raise OpenAIAPIError(
                "Responses API request timed out",
                retryable=True,
            ) from error
        except json.JSONDecodeError as error:
            raise OpenAIAPIError(
                "Responses API returned invalid JSON",
            ) from error
        if not isinstance(value, dict):
            raise OpenAIAPIError("Responses API returned a non-object payload")
        return value


def _retry_after_seconds(headers: Message | None) -> float | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


__all__ = [
    "OpenAIAPIError",
    "OpenAIResponseResult",
    "OpenAIResponsesClient",
    "RESPONSES_URL",
    "Transport",
]
