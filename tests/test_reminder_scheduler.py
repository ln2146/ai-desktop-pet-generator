from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.reminder import parse_dt  # noqa: E402
from petgen.reminder_scheduler import ReminderScheduler  # noqa: E402
from petgen.store import ReminderStore  # noqa: E402

T = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-reminder-scheduler"])


def _make(tmp_path: Path):
    store = ReminderStore(tmp_path / "db.sqlite")
    sched = ReminderScheduler(store)
    return store, sched


def test_create_persists_and_signals(qapp, tmp_path: Path) -> None:
    store, sched = _make(tmp_path)
    changed: list[bool] = []
    sched.reminders_changed.connect(lambda: changed.append(True))
    r = sched.create("喝水", T("2026-03-01T09:00:00"))
    assert r.id and store.get(r.id) is not None
    assert changed == [True]


def test_check_due_emits_for_due_only(qapp, tmp_path: Path) -> None:
    store, sched = _make(tmp_path)
    sched.create("过去", T("2026-03-01T09:00:00"))
    sched.create("将来", T("2026-12-01T09:00:00"))
    due: list = []
    sched.reminder_due.connect(lambda r: due.append(r.id))
    result = sched.check_due(T("2026-03-01T10:00:00"))
    assert [r.id for r in result] == [r.id for r in result]
    assert len(due) == 1
    # not re-emitted (handled)
    assert sched.check_due(T("2026-03-01T10:30:00")) == []


def test_complete_one_shot_marks_completed(qapp, tmp_path: Path) -> None:
    store, sched = _make(tmp_path)
    r = sched.create("一次性", T("2026-03-01T09:00:00"))
    completed: list = []
    sched.reminder_completed.connect(lambda x: completed.append(x.id))
    sched.complete(r.id)
    assert completed == [r.id]
    assert store.get(r.id).status == "completed"


def test_complete_recurring_rolls_forward(qapp, tmp_path: Path) -> None:
    store, sched = _make(tmp_path)
    r = sched.create("每天", T("2026-03-01T09:00:00"), recurrence="daily")
    completed: list = []
    sched.reminder_completed.connect(lambda x: completed.append(x.id))
    sched.complete(r.id)
    assert completed == []  # not completed, rolled forward
    rolled = store.get(r.id)
    assert rolled.status == "scheduled"
    assert parse_dt(rolled.trigger_at) == T("2026-03-02T09:00:00")


def test_snooze_defers_and_clears_handled(qapp, tmp_path: Path) -> None:
    store, sched = _make(tmp_path)
    r = sched.create("延后", T("2026-03-01T09:00:00"))
    sched.check_due(T("2026-03-01T10:00:00"))  # marks handled
    sched.snooze(r.id, minutes=10, now=T("2026-03-01T10:00:00"))
    snoozed = store.get(r.id)
    assert snoozed.status == "snoozed"
    assert parse_dt(snoozed.snooze_until) == T("2026-03-01T10:10:00")
    # handled cleared, but not due until snooze time
    assert sched.check_due(T("2026-03-01T10:05:00")) == []
    assert len(sched.check_due(T("2026-03-01T10:10:00"))) == 1


def test_delete(qapp, tmp_path: Path) -> None:
    store, sched = _make(tmp_path)
    r = sched.create("删我", T("2026-03-01T09:00:00"))
    changed: list = []
    sched.reminders_changed.connect(lambda: changed.append(1))
    assert sched.delete(r.id) is True
    assert store.get(r.id) is None
    assert changed


def test_update_edits_fields_resets_handled_and_signals(qapp, tmp_path: Path) -> None:
    import sqlite3

    store, sched = _make(tmp_path)
    r = sched.create("旧标题", T("2026-03-01T09:00:00"))
    # Simulate a previously-fired reminder (due_handled=1) via raw SQL.
    raw = sqlite3.connect(str(tmp_path / "db.sqlite"))
    raw.execute("UPDATE reminders SET due_handled = 1 WHERE id = ?", (r.id,))
    raw.commit()
    raw.close()

    changed: list = []
    sched.reminders_changed.connect(lambda: changed.append(1))
    updated = sched.update(
        r.id,
        title="新标题",
        trigger_at=T("2026-04-01T08:00:00"),
        recurrence="daily",
    )

    assert updated is not None
    assert updated.title == "新标题"
    assert updated.recurrence == "daily"
    assert parse_dt(updated.trigger_at) == T("2026-04-01T08:00:00")
    assert changed  # reminders_changed emitted
    raw = sqlite3.connect(str(tmp_path / "db.sqlite"))
    handled = raw.execute("SELECT due_handled FROM reminders WHERE id = ?", (r.id,)).fetchone()[0]
    raw.close()
    assert handled == 0  # reset so the edited time can fire


def test_update_missing_returns_none(qapp, tmp_path: Path) -> None:
    store, sched = _make(tmp_path)
    assert sched.update("no-such-id", title="x", trigger_at=T("2026-03-01T09:00:00")) is None
