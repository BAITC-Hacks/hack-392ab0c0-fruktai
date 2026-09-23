"""Small standard-library client used by integration scripts and demos."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BackendAPIError(RuntimeError):
    """Raised when the backend cannot complete a requested operation."""


def health(base_url: str, timeout: float = 5.0) -> dict[str, Any]:
    return _request_json("GET", f"{base_url.rstrip('/')}/health", timeout=timeout)


def recalculate(
    base_url: str,
    dataset: str = "demo",
    overrides: list[dict[str, Any]] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    payload = {"dataset": dataset, "overrides": overrides or []}
    return _request_json(
        "POST",
        f"{base_url.rstrip('/')}/api/v1/recalculate",
        payload,
        timeout,
    )


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise BackendAPIError(f"{method} {url} returned {error.code}: {detail}") from error
    except URLError as error:
        raise BackendAPIError(f"Cannot reach backend at {url}: {error.reason}") from error
    if not isinstance(value, dict):
        raise BackendAPIError(f"{method} {url} returned a non-object JSON response")
    return value

