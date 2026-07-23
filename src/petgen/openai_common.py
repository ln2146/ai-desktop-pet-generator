"""Shared helpers for the OpenAI-compatible image and text clients."""

from __future__ import annotations

from typing import Any

import requests

# Cap on the response body excerpt included in error messages, so a huge error
# payload cannot blow up logs / bubbles.
_MAX_ERROR_BODY_CHARS = 600


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
