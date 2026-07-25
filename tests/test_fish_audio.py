from __future__ import annotations

from pathlib import Path

import pytest

from petgen.fish_audio import (
    FISH_FREE_TTS_MODEL,
    FishAudioError,
    FishAudioTTSClient,
    FishAudioTTSConfig,
)


class _FakeResponse:
    def __init__(self, status_code: int, chunks: list[bytes], payload: dict | None = None) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self._payload = payload
        self.text = "raw error"

    def iter_content(self, chunk_size: int):
        assert chunk_size > 0
        yield from self._chunks

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


def test_fish_audio_tts_uses_free_model_and_reference_id(tmp_path: Path) -> None:
    session = _FakeSession(_FakeResponse(200, [b"mp3", b"-bytes"]))
    config = FishAudioTTSConfig(api_key="fish-key", base_url="https://example.test")

    path = tmp_path / "voice.mp3"
    FishAudioTTSClient(config, session=session).synthesize_to_file("  你好  ", path, reference_id="voice-id")

    assert path.read_bytes() == b"mp3-bytes"
    call = session.calls[0]
    assert call["url"] == "https://example.test/v1/tts"
    assert call["headers"]["Authorization"] == "Bearer fish-key"
    assert call["headers"]["model"] == FISH_FREE_TTS_MODEL
    assert call["json"]["text"] == "你好"
    assert call["json"]["reference_id"] == "voice-id"
    assert call["json"]["format"] == "mp3"


def test_fish_audio_tts_surfaces_api_errors(tmp_path: Path) -> None:
    session = _FakeSession(_FakeResponse(401, [], {"message": "bad key"}))
    client = FishAudioTTSClient(FishAudioTTSConfig(api_key="fish-key"), session=session)

    with pytest.raises(FishAudioError, match="bad key"):
        client.synthesize_to_file("你好", tmp_path / "voice.mp3")


def test_fish_audio_config_reads_supported_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    monkeypatch.setenv("FISH_API_KEY", "from-env")

    assert FishAudioTTSConfig.from_env().api_key == "from-env"

    monkeypatch.setenv("FISH_AUDIO_API_KEY", "preferred-env")
    assert FishAudioTTSConfig.from_env().api_key == "preferred-env"
