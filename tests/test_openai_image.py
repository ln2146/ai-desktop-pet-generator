from __future__ import annotations

import base64

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
