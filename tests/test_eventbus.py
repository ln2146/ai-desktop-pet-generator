from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from petgen.eventbus import TaskEvent, expression_for_kind, parse_event_line


@pytest.mark.parametrize(
    "kind, expected",
    [
        ("ai_thinking", "busy"),
        ("ai_responding", "attentive"),
        ("ai_waiting", "idle"),
        ("ai_idle", "idle"),
        ("ai_error", "error"),
        ("task_completed", "happy"),
        ("custom", "happy"),
    ],
)
def test_expression_for_kind_known(kind: str, expected: str) -> None:
    assert expression_for_kind(kind) == expected


@pytest.mark.parametrize("kind", ["nonsense", "", "AI_THINKING", "done"])
def test_expression_for_kind_unknown_degrades_to_happy(kind: str) -> None:
    assert expression_for_kind(kind) == "happy"


def test_parse_event_line_valid() -> None:
    line = '{"id":"x1","kind":"task_completed","title":"hi","detail":"d","source":"manual","createdAt":"2026-01-01T00:00:00Z"}'
    event = parse_event_line(line)
    assert isinstance(event, TaskEvent)
    assert event.id == "x1"
    assert event.kind == "task_completed"
    assert event.title == "hi"
    assert event.detail == "d"
    assert event.source == "manual"


def test_parse_event_line_fills_missing_id_and_time() -> None:
    event = parse_event_line('{"kind":"ai_thinking","title":"t"}')
    assert event is not None
    assert event.id  # generated
    assert event.created_at  # generated


def test_parse_event_line_unknown_kind_kept() -> None:
    event = parse_event_line('{"kind":"weird_new_kind","title":"t"}')
    assert event is not None and event.kind == "weird_new_kind"


@pytest.mark.parametrize("line", ["not json", "", '{"title":"no kind"}', '{"kind":123}', "[]"])
def test_parse_event_line_bad_returns_none(line: str) -> None:
    assert parse_event_line(line) is None


def test_display_message_with_and_without_source() -> None:
    ev = TaskEvent("id", "task_completed", "搞定", None, "claude_code", "t")
    assert ev.display_message() == "[Claude Code] 搞定"
    ev2 = TaskEvent("id", "ai_error", "出错", "详情", "manual", "t")
    assert ev2.display_message() == "出错：详情"


# --- Qt poller (offscreen) --------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.eventbus import EventBus  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-eventbus"])


def _line(**fields) -> str:
    base = {"id": "auto", "kind": "task_completed", "title": "t", "createdAt": "2026-01-01T00:00:00Z"}
    base.update(fields)
    return json.dumps(base, ensure_ascii=False)


def test_poll_now_emits_valid_and_warns_on_garbage(qapp, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.jsonl"
    inbox.write_text(
        _line(id="a", kind="ai_thinking", title="thinking")
        + "\n"
        + "garbage line\n"
        + _line(id="b", kind="task_completed", title="done")
        + "\n",
        encoding="utf-8",
    )
    bus = EventBus(inbox=inbox, state=tmp_path / "state.json", parent=qapp)
    got: list[TaskEvent] = []
    warns: list[str] = []
    bus.event_received.connect(lambda e: got.append(e))
    bus.warnings.connect(lambda w: warns.extend(w))

    emitted = bus.poll_now()

    assert [e.id for e in emitted] == ["a", "b"]
    assert got[0].kind == "ai_thinking"
    assert expression_for_kind(got[0].kind) == "busy"
    assert len(warns) == 1 and "garbage line" in warns[0]


def test_poll_now_dedups_by_id(qapp, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.jsonl"
    inbox.write_text(_line(id="dup", title="one") + "\n", encoding="utf-8")
    bus = EventBus(inbox=inbox, state=tmp_path / "state.json", parent=qapp)
    got: list[TaskEvent] = []
    bus.event_received.connect(lambda e: got.append(e))

    bus.poll_now()
    with inbox.open("a", encoding="utf-8") as handle:
        handle.write(_line(id="dup", title="again") + "\n")
    second = bus.poll_now()

    assert second == []
    assert len(got) == 1


def test_poll_now_leaves_partial_line_unconsumed(qapp, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.jsonl"
    partial = _line(id="p", title="partial")
    inbox.write_text(partial, encoding="utf-8")  # no trailing newline
    bus = EventBus(inbox=inbox, state=tmp_path / "state.json", parent=qapp)
    got: list[TaskEvent] = []
    bus.event_received.connect(lambda e: got.append(e))

    assert bus.poll_now() == []
    assert got == []

    with inbox.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    bus.poll_now()
    assert [e.id for e in got] == ["p"]


def test_poll_now_resets_offset_after_truncation(qapp, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.jsonl"
    inbox.write_text(_line(id="first", title="a longish title to make this line big") + "\n", encoding="utf-8")
    bus = EventBus(inbox=inbox, state=tmp_path / "state.json", parent=qapp)
    got: list[TaskEvent] = []
    bus.event_received.connect(lambda e: got.append(e))
    bus.poll_now()
    big_offset = bus._offset

    # overwrite with a SHORTER file → size < offset triggers a reset + re-read
    inbox.write_text(_line(id="x") + "\n", encoding="utf-8")
    assert inbox.stat().st_size < big_offset
    bus.poll_now()

    assert [e.id for e in got] == ["first", "x"]


def test_offset_persists_across_instances(qapp, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox.jsonl"
    state = tmp_path / "state.json"
    inbox.write_text(_line(id="persist") + "\n", encoding="utf-8")
    bus1 = EventBus(inbox=inbox, state=state, parent=qapp)
    bus1.poll_now()

    bus2 = EventBus(inbox=inbox, state=state, parent=qapp)
    got: list[TaskEvent] = []
    bus2.event_received.connect(lambda e: got.append(e))
    with inbox.open("a", encoding="utf-8") as handle:
        handle.write(_line(id="new") + "\n")
    bus2.poll_now()

    assert [e.id for e in got] == ["new"]


def test_hook_script_appends_valid_line(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "petgen-event.sh"
    if not script.exists():
        pytest.skip("hook script not present")
    env = {**os.environ, "PETGEN_DATA_DIR": str(tmp_path)}
    subprocess.run(
        ["bash", str(script), "task_completed", "完成啦", "一些细节", "claude_code"],
        env=env,
        check=True,
    )
    inbox = tmp_path / "task-events.jsonl"
    lines = inbox.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = parse_event_line(lines[0])
    assert event is not None
    assert event.kind == "task_completed"
    assert event.title == "完成啦"
    assert event.detail == "一些细节"
    assert event.source == "claude_code"
