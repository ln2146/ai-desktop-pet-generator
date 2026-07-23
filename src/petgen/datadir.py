from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Resolve (and create) the petgen data directory.

    ``$PETGEN_DATA_DIR`` wins when set so a shell hook and the app agree on one
    path; otherwise ``~/.petgen`` is used (kept cross-platform and trivially
    reproducible from the event-hook script).
    """
    override = os.environ.get("PETGEN_DATA_DIR")
    base = Path(override).expanduser() if override else Path.home() / ".petgen"
    base.mkdir(parents=True, exist_ok=True)
    return base


def pets_root() -> Path:
    root = data_dir() / "pets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return data_dir() / "petgen.sqlite"


def event_inbox_path() -> Path:
    return data_dir() / "task-events.jsonl"


def event_state_path() -> Path:
    return data_dir() / "task-events.state.json"
