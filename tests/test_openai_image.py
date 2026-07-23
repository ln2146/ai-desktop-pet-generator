from __future__ import annotations

import base64

import pytest

from petgen.openai_image import ImageRequestConfig, OpenAIImageClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.content = b""

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse(
            200,
            {"data": [{"b64_json": base64.b64encode(b"png-bytes").decode("ascii")}]},
        )


def test_text_generation_uses_generations_endpoint() -> None:
    session = FakeSession()
    client = OpenAIImageClient(
        ImageRequestConfig(api_key="test", base_url="https://example.test/v1", model="gpt-image-2"),
        session=session,  # type: ignore[arg-type]
    )
    assert client.generate("draw pet") == b"png-bytes"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.endswith("/images/generations")
    assert kwargs["json"]["model"] == "gpt-image-2"
    assert kwargs["json"]["prompt"] == "draw pet"


class _QueuedSession:
    """Returns pre-loaded responses in order; records how many posts happened."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.posts = 0

    def post(self, url: str, **kwargs):
        self.posts += 1
        return self._responses.pop(0)


def test_image_retries_on_503_then_succeeds(monkeypatch) -> None:
    import petgen.openai_common as oc

    monkeypatch.setattr(oc, "_retry_sleep", lambda _s: None)
    session = _QueuedSession(
        [
            FakeResponse(503, {"error": "overloaded"}),
            FakeResponse(503, {"error": "still overloaded"}),
            FakeResponse(200, {"data": [{"b64_json": base64.b64encode(b"ok").decode()}]}),
        ]
    )
    client = OpenAIImageClient(
        ImageRequestConfig(api_key="test", max_attempts=3), session=session  # type: ignore[arg-type]
    )
    assert client.generate("pet") == b"ok"
    assert session.posts == 3


def test_image_retry_exhausted_raises(monkeypatch) -> None:
    import petgen.openai_common as oc
    import petgen.openai_image as oi

    monkeypatch.setattr(oc, "_retry_sleep", lambda _s: None)
    session = _QueuedSession([FakeResponse(500, {"error": "boom"})] * 3)
    client = OpenAIImageClient(
        ImageRequestConfig(api_key="test", max_attempts=3), session=session  # type: ignore[arg-type]
    )
    with pytest.raises(oi.ImageGenerationError):
        client.generate("pet")
    assert session.posts == 3
