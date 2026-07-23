from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


class TextGenerationError(RuntimeError):
    """Raised when the text (chat) API request or response is not usable."""


ENRICH_MIN_DESCRIPTION_CHARS = 30

ENRICH_SYSTEM_PROMPT = """
You enrich short pet character descriptions for a desktop-pet generator.

Rules:
- Expand ONLY the pet's concept, species, appearance, colors, markings, accessories, personality, and art style.
- Never mention spritesheets, frames, rows, grids, canvases, backgrounds, green screens, or layout.
- Keep the user's original language.
- Reply with ONLY the enriched description as one plain paragraph: no preamble, no quotes, no bullet lists.
- Stay faithful to the user's intent and keep it under about 120 characters.
""".strip()


@dataclass(frozen=True)
class TextRequestConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 60

    @classmethod
    def from_env(
        cls,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> "TextRequestConfig":
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not resolved_key:
            raise TextGenerationError(
                "OPENAI_API_KEY is required. Set it in the environment or pass --api-key."
            )
        return cls(
            api_key=resolved_key,
            base_url=(base_url or os.environ.get("OPENAI_BASE_URL") or cls.base_url).rstrip("/"),
            model=model or os.environ.get("OPENAI_TEXT_MODEL") or cls.model,
        )


class OpenAITextClient:
    """Small OpenAI-compatible Chat Completions client.

    Used to enrich short pet descriptions before image generation. The session is
    injectable so tests can verify requests without touching the network.
    """

    def __init__(self, config: TextRequestConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    def complete(self, *, system: str, user: str) -> str:
        response = self.session.post(
            f"{self.config.base_url}/chat/completions",
            headers=self._json_headers(),
            json={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 500,
            },
            timeout=self.config.timeout_seconds,
        )
        return self._extract_text(response)

    def enrich(self, description: str) -> str:
        return self.complete(system=ENRICH_SYSTEM_PROMPT, user=description)

    def _json_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _extract_text(self, response: requests.Response) -> str:
        if response.status_code < 200 or response.status_code >= 300:
            raise TextGenerationError(_format_http_error(response))

        try:
            payload = response.json()
        except ValueError as exc:
            raise TextGenerationError("text API returned non-JSON response") from exc

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise TextGenerationError("text API response did not contain choices[0]")

        first = choices[0]
        if not isinstance(first, dict):
            raise TextGenerationError("text API response choices[0] is not an object")

        message = first.get("message")
        if not isinstance(message, dict):
            raise TextGenerationError("text API response choices[0].message is not an object")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise TextGenerationError("text API response did not include usable message content")

        return content.strip()


def should_enrich(description: str, flag: bool | None) -> bool:
    """Decide whether to enrich a description.

    An explicit flag (``--enrich`` / ``--no-enrich``) always wins. Otherwise short
    descriptions are enriched automatically.
    """
    if flag is not None:
        return flag
    return len(description.strip()) < ENRICH_MIN_DESCRIPTION_CHARS


def _format_http_error(response: requests.Response) -> str:
    body: Any
    try:
        body = response.json()
    except ValueError:
        body = response.text
    text = str(body)
    if len(text) > 600:
        text = text[:600] + "..."
    return f"text API request failed with HTTP {response.status_code}: {text}"
