from __future__ import annotations

import os
from pathlib import Path

from petgen.envfile import load_env_file


def test_load_env_file_without_overriding_existing_values(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=from-file",
                "OPENAI_BASE_URL=\"https://example.test/v1\"",
                "OPENAI_IMAGE_MODEL='gpt-image-2'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "already-set")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_IMAGE_MODEL", raising=False)

    loaded = load_env_file(env_path)

    assert loaded == env_path
    assert os.environ["OPENAI_API_KEY"] == "already-set"
    assert os.environ["OPENAI_BASE_URL"] == "https://example.test/v1"
    assert os.environ["OPENAI_IMAGE_MODEL"] == "gpt-image-2"
