from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path | None = None) -> Path | None:
    """Load simple KEY=VALUE pairs from .env without overriding existing env vars."""
    env_path = path or _default_env_path()
    if env_path is None or not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid .env line: {raw_line}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        if not key:
            raise ValueError(f"invalid .env line: {raw_line}")
        os.environ.setdefault(key, value)
    return env_path


def _default_env_path() -> Path | None:
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
    package_env = Path(__file__).resolve().parents[2] / ".env"
    if package_env.exists():
        return package_env
    return None


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
