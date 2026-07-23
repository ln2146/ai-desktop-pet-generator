from __future__ import annotations

import os

import pytest

from petgen.openai_text import (
    ENRICH_MIN_DESCRIPTION_CHARS,
    ENRICH_SYSTEM_PROMPT,
    OpenAITextClient,
    TextGenerationError,
    TextRequestConfig,
    should_enrich,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text else str(payload)
        self.content = b""

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.response = response or FakeResponse(
            200, {"choices": [{"message": {"content": "enriched description"}}]}
        )

    def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.response


def _client(session: FakeSession) -> OpenAITextClient:
    return OpenAITextClient(
        TextRequestConfig(api_key="test", base_url="https://example.test/v1", model="gpt-4o-mini"),
        session=session,  # type: ignore[arg-type]
    )


def test_complete_posts_chat_completions_request() -> None:
    session = FakeSession()
    client = _client(session)

    result = client.complete(system="system text", user="user text")

    assert result == "enriched description"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.endswith("/chat/completions")
    assert kwargs["headers"]["Authorization"] == "Bearer test"
    body = kwargs["json"]
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"][0] == {"role": "system", "content": "system text"}
    assert body["messages"][1] == {"role": "user", "content": "user text"}


def test_complete_returns_stripped_content() -> None:
    session = FakeSession(
        FakeResponse(200, {"choices": [{"message": {"content": "  padded text  \n"}}]})
    )
    assert _client(session).complete(system="s", user="u") == "padded text"


def test_enrich_uses_enrich_system_prompt() -> None:
    session = FakeSession()
    _client(session).enrich("一只猫")

    system_message = session.calls[0][2]["json"]["messages"][0]
    assert system_message["content"] == ENRICH_SYSTEM_PROMPT
    assert "green screen" in ENRICH_SYSTEM_PROMPT


def test_http_error_raises_text_generation_error() -> None:
    session = FakeSession(FakeResponse(400, {"error": {"message": "bad model"}}))
    try:
        _client(session).complete(system="s", user="u")
    except TextGenerationError as exc:
        assert "HTTP 400" in str(exc)
    else:
        raise AssertionError("expected TextGenerationError")


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "   "}}]},
        {"choices": []},
        {},
    ],
)
def test_unusable_response_shapes_raise(payload: dict) -> None:
    session = FakeSession(FakeResponse(200, payload))
    with pytest.raises(TextGenerationError):
        _client(session).complete(system="s", user="u")


def test_non_json_response_raises() -> None:
    session = FakeSession(FakeResponse(200, payload=None, text="<html>oops</html>"))
    with pytest.raises(TextGenerationError):
        _client(session).complete(system="s", user="u")


def _clear_text_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)


def test_from_env_defaults_to_gpt_4o_mini(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_text_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    config = TextRequestConfig.from_env()

    assert config.api_key == "from-env"
    assert config.model == "gpt-4o-mini"
    assert config.base_url == "https://api.openai.com/v1"


def test_from_env_reads_text_model_and_strips_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_text_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "custom-text-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example.test/v1/")

    config = TextRequestConfig.from_env()

    assert config.model == "custom-text-model"
    assert config.base_url == "https://proxy.example.test/v1"


def test_from_env_explicit_arguments_win(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_text_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "env-model")

    config = TextRequestConfig.from_env(api_key="explicit", model="explicit-model")

    assert config.api_key == "explicit"
    assert config.model == "explicit-model"


def test_from_env_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_text_env(monkeypatch)
    with pytest.raises(TextGenerationError):
        TextRequestConfig.from_env()


LONG_DESCRIPTION = "一只圆滚滚的水豚程序员，戴小耳机，背着小小的代码背包，性格温柔、专注、聪明，适合陪伴写代码"


def test_should_enrich_auto_depends_on_length() -> None:
    assert len(LONG_DESCRIPTION) >= ENRICH_MIN_DESCRIPTION_CHARS
    assert should_enrich("一只猫", None) is True
    assert should_enrich(LONG_DESCRIPTION, None) is False


def test_should_enrich_boundary_is_strictly_less_than_threshold() -> None:
    exact = "猫" * ENRICH_MIN_DESCRIPTION_CHARS
    assert len(exact) == ENRICH_MIN_DESCRIPTION_CHARS
    assert should_enrich(exact, None) is False
    assert should_enrich(exact[:-1], None) is True


def test_should_enrich_flag_overrides_length() -> None:
    assert should_enrich(LONG_DESCRIPTION, True) is True
    assert should_enrich("一只猫", False) is False


def test_should_enrich_measures_stripped_length() -> None:
    padded = "   " + "猫" * ENRICH_MIN_DESCRIPTION_CHARS + "  \n"
    assert should_enrich(padded, None) is False


class _QueuedSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.posts = 0

    def post(self, url: str, **kwargs):
        self.posts += 1
        return self._responses.pop(0)


def _retry_client(session: _QueuedSession) -> OpenAITextClient:
    return OpenAITextClient(
        TextRequestConfig(api_key="test", base_url="https://example.test/v1", max_attempts=3),
        session=session,  # type: ignore[arg-type]
    )


def test_text_retries_on_429_then_succeeds(monkeypatch) -> None:
    import petgen.openai_common as oc

    monkeypatch.setattr(oc, "_retry_sleep", lambda _s: None)
    session = _QueuedSession(
        [
            FakeResponse(429, {"error": "rate limited"}),
            FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    assert _retry_client(session).complete(system="s", user="u") == "ok"
    assert session.posts == 2


def test_text_retry_exhausted_raises(monkeypatch) -> None:
    import petgen.openai_common as oc

    monkeypatch.setattr(oc, "_retry_sleep", lambda _s: None)
    session = _QueuedSession([FakeResponse(502, {"error": "bad gateway"})] * 3)
    with pytest.raises(TextGenerationError):
        _retry_client(session).complete(system="s", user="u")
    assert session.posts == 3
