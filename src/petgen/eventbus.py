from __future__ import annotations

import json
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from petgen.datadir import event_inbox_path, event_state_path

EXPRESSION_FOR_KIND = {
    "ai_thinking": "busy",
    "ai_responding": "attentive",
    "ai_waiting": "idle",
    "ai_idle": "idle",
    "ai_error": "error",
    "task_completed": "happy",
    "custom": "happy",
}

_SOURCE_LABELS = {
    "claude_code": "Claude Code",
    "codex": "Codex",
    "copilot": "Copilot",
    "glm": "GLM",
    "manual": "",
}

# A single inbox line larger than this is treated as malformed and skipped in
# full (the byte range is consumed so a runaway writer cannot pin the reader at
# a never-advancing offset and grow memory on every poll).
_MAX_LINE_BYTES = 64 * 1024


def expression_for_kind(kind: str) -> str:
    """Map an event kind to a pet expression; unknown kinds degrade to happy."""
    return EXPRESSION_FOR_KIND.get(kind, "happy")


@dataclass(frozen=True)
class TaskEvent:
    id: str
    kind: str
    title: str
    detail: str | None
    source: str | None
    created_at: str

    def display_message(self) -> str:
        label = _SOURCE_LABELS.get(self.source or "", "")
        prefix = f"[{label}] " if label else ""
        body = self.title or self.kind
        if self.detail:
            body = f"{body}：{self.detail}"
        return f"{prefix}{body}"


def parse_event_line(line: str) -> TaskEvent | None:
    """Parse one JSONL line tolerantly; returns None for unusable lines."""
    text = line.strip()
    if not text:
        return None
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    if not isinstance(kind, str) or not kind:
        return None
    event_id = raw.get("id")
    if not isinstance(event_id, str) or not event_id:
        event_id = str(uuid.uuid4())
    created_at = raw.get("createdAt")
    if not isinstance(created_at, str) or not created_at:
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = raw.get("title")
    detail = raw.get("detail")
    source = raw.get("source")
    return TaskEvent(
        id=event_id,
        kind=kind,
        title=str(title) if title is not None else "",
        detail=str(detail) if detail is not None else None,
        source=str(source) if source is not None else None,
        created_at=created_at,
    )


# --- Qt-dependent poller; only defined when PySide6 is importable -------------
try:  # pragma: no cover - import-time branch
    from PySide6.QtCore import QObject, QTimer, Signal

    class EventBus(QObject):
        """Polls a JSONL inbox and emits parsed task events (mirrors TaskEventInbox)."""

        event_received = Signal(object)
        warnings = Signal(list)

        def __init__(
            self,
            inbox: Path | None = None,
            state: Path | None = None,
            interval_ms: int = 2000,
            parent=None,
        ) -> None:
            super().__init__(parent)
            self._inbox = inbox or event_inbox_path()
            self._state = state or event_state_path()
            self._interval_ms = interval_ms
            self._offset = self._load_offset()
            self._seen: deque[str] = deque(maxlen=500)
            self._timer = QTimer(self)
            self._timer.setInterval(interval_ms)
            self._timer.timeout.connect(self.poll_now)

        def start(self) -> None:
            self.poll_now()
            self._timer.start()

        def stop(self) -> None:
            self._timer.stop()

        def poll_now(self) -> list[TaskEvent]:
            """Incrementally read the inbox once; return the newly emitted events.

            The inbox is read as *bytes* and split on ``b"\\n"`` so the consumed
            offset is always a byte count (the previous char-based accounting
            under-advanced on multibyte (Chinese) titles, drifting the offset and
            re-reading fragments). Oversized lines are skipped in full and
            malformed lines are reported as a single aggregated warning per poll
            rather than one signal each (a hostile writer could otherwise flood
            the GUI thread with emits).
            """
            try:
                if not self._inbox.exists():
                    return []
                size = self._inbox.stat().st_size
                if size < self._offset:
                    self._offset = 0  # file was truncated/rotated
                with self._inbox.open("rb") as handle:
                    handle.seek(self._offset)
                    chunk = handle.read()
            except OSError as exc:
                self.warnings.emit([f"event inbox read failed: {exc}"])
                return []

            if not chunk:
                return []

            last_nl = chunk.rfind(b"\n")
            if last_nl == -1:
                # No complete line yet. If the pending tail already exceeds the
                # per-line cap it can never become a valid line, so drop it
                # (advancing the offset) instead of buffering it forever.
                if len(chunk) > _MAX_LINE_BYTES:
                    self._offset += len(chunk)
                    self._save_offset()
                    self.warnings.emit(["dropped oversized event line (>64KiB)"])
                return []
            complete = chunk[: last_nl + 1]
            leftover = chunk[last_nl + 1 :]

            emitted: list[TaskEvent] = []
            dropped = 0
            first_bad = ""
            for raw in complete.split(b"\n"):
                if not raw:
                    continue
                if len(raw) > _MAX_LINE_BYTES:
                    dropped += 1
                    if not first_bad:
                        first_bad = "<oversized line>"
                    continue
                line = raw.decode("utf-8", errors="replace")
                event = parse_event_line(line)
                if event is None:
                    dropped += 1
                    if not first_bad:
                        first_bad = line[:120]
                    continue
                if event.id in self._seen:
                    continue
                self._seen.append(event.id)
                emitted.append(event)
                self.event_received.emit(event)

            if dropped:
                detail = f"; first: {first_bad}" if first_bad else ""
                self.warnings.emit([f"dropped {dropped} malformed event line(s){detail}"])

            self._offset += len(complete)
            # leftover (a partial line, possibly ending mid multibyte char) stays
            # on disk and is re-read from the unchanged offset next poll.
            del leftover
            self._save_offset()
            return emitted

        def _load_offset(self) -> int:
            try:
                raw = json.loads(self._state.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return 0
            if isinstance(raw, dict):
                value = raw.get("lastReadOffset")
                if isinstance(value, int) and value >= 0:
                    return value
            return 0

        def _save_offset(self) -> None:
            self._state.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"lastReadOffset": self._offset}), encoding="utf-8")
            tmp.replace(self._state)

except ImportError:  # pragma: no cover - PySide6 absent
    EventBus = None  # type: ignore[assignment,misc]
