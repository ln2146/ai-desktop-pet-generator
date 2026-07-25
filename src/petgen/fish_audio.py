from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

FISH_FREE_TTS_MODEL = "s2.1-pro-free"
FISH_API_BASE_URL = "https://api.fish.audio"


class FishAudioError(RuntimeError):
    """Raised when Fish Audio rejects or fails a synthesis request."""


@dataclass(frozen=True)
class FishAudioTTSConfig:
    api_key: str
    base_url: str = FISH_API_BASE_URL
    model: str = FISH_FREE_TTS_MODEL
    timeout: float = 45.0

    @classmethod
    def from_env(
        cls,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> "FishAudioTTSConfig":
        resolved_key = api_key or os.environ.get("FISH_AUDIO_API_KEY") or os.environ.get("FISH_API_KEY") or ""
        return cls(
            api_key=resolved_key.strip(),
            base_url=(base_url or os.environ.get("FISH_AUDIO_BASE_URL") or FISH_API_BASE_URL).rstrip("/"),
            model=model or os.environ.get("FISH_AUDIO_TTS_MODEL") or FISH_FREE_TTS_MODEL,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


class FishAudioTTSClient:
    """Small REST client for Fish Audio's text-to-speech endpoint."""

    def __init__(self, config: FishAudioTTSConfig, *, session: Any | None = None) -> None:
        if not config.api_key:
            raise FishAudioError("Fish Audio API key is required")
        self.config = config
        self._session = session or requests.Session()

    def synthesize_to_file(self, text: str, path: str | Path, *, reference_id: str | None = None) -> None:
        clean_text = text.strip()
        if not clean_text:
            raise FishAudioError("Text is required")

        payload: dict[str, Any] = {
            "text": clean_text,
            "temperature": 0.7,
            "top_p": 0.7,
            "prosody": {"speed": 1, "volume": 0, "normalize_loudness": True},
            "chunk_length": 300,
            "normalize": True,
            "format": "mp3",
            "sample_rate": 44100,
            "mp3_bitrate": 128,
            "latency": "normal",
            "max_new_tokens": 1024,
            "repetition_penalty": 1.2,
            "min_chunk_length": 50,
            "condition_on_previous_chunks": True,
            "early_stop_threshold": 1,
        }
        if reference_id:
            payload["reference_id"] = reference_id

        response = self._session.post(
            f"{self.config.base_url}/v1/tts",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "model": self.config.model,
            },
            json=payload,
            timeout=self.config.timeout,
            stream=True,
        )
        if response.status_code != 200:
            raise FishAudioError(self._error_message(response))

        target = Path(path)
        total = 0
        with target.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                fh.write(chunk)
        if total == 0:
            raise FishAudioError("Fish Audio returned an empty audio response")

    @staticmethod
    def _error_message(response: Any) -> str:
        try:
            data = response.json()
        except Exception:
            data = None
        if isinstance(data, dict) and data.get("message"):
            return f"Fish Audio TTS failed: {data['message']}"
        text = getattr(response, "text", "")
        if text:
            return f"Fish Audio TTS failed: HTTP {response.status_code}: {text[:200]}"
        return f"Fish Audio TTS failed: HTTP {response.status_code}"
