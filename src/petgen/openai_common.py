"""Shared helpers for the OpenAI-compatible image and text clients."""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

# Cap on the response body excerpt included in error messages, so a huge error
# payload cannot blow up logs / bubbles.
_MAX_ERROR_BODY_CHARS = 600

# HTTP statuses worth retrying (rate limit / server-side / overload).
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Default retry policy: 3 tries total with 1s then 2s backoff.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.0

# Module-level sleep so tests can monkeypatch it (set to a no-op) without the
# client call sites having to thread a sleep argument through.
_retry_sleep: Callable[[float], None] = time.sleep


class _RetryableStatus(RuntimeError):
    """Internal: a response status that should trigger another attempt."""


def format_http_error(response: requests.Response, *, label: str) -> str:
    """Build a readable error string for a non-2xx API response.

    ``label`` is the human-facing API name (e.g. "image", "text") so the two
    clients can share one implementation without duplicating the body parsing.
    """
    body: Any
    try:
        body = response.json()
    except ValueError:
        body = response.text
    text = str(body)
    if len(text) > _MAX_ERROR_BODY_CHARS:
        text = text[:_MAX_ERROR_BODY_CHARS] + "..."
    return f"{label} API request failed with HTTP {response.status_code}: {text}"


def with_retry(
    request: Callable[[], requests.Response],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> requests.Response:
    """Run ``request`` with retries on transient failures.

    Retries on connection/timeout errors and on ``_RETRYABLE_STATUSES`` (429/5xx)
    with linear backoff; re-raises the last error when attempts are exhausted.
    Non-retryable HTTP errors (e.g. 4xx) are returned to the caller unchanged so
    its own error formatting runs. The backoff sleep goes through the module-level
    ``_retry_sleep`` so tests can monkeypatch it to a no-op.
    """
    attempts = max(1, int(max_attempts))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            response = request()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                _retry_sleep(backoff_seconds * (attempt + 1))
                continue
            raise
        if response.status_code in _RETRYABLE_STATUSES:
            last_exc = _RetryableStatus(format_http_error(response, label="retry"))
            if attempt + 1 < attempts:
                _retry_sleep(backoff_seconds * (attempt + 1))
                continue
            raise requests.HTTPError(str(last_exc), response=response)
        return response
    # Unreachable: the loop always returns or raises, but satisfy type checkers.
    if last_exc is not None:  # pragma: no cover
        raise last_exc
    raise RuntimeError("with_retry: no attempts made")  # pragma: no cover

