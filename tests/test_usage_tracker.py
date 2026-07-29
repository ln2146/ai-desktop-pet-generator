from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from datetime import datetime, timedelta, timezone  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.usage_tracker import UsageTracker  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-usage-tracker"])


def _now() -> datetime:
    return datetime(2026, 7, 30, 10, 0, 0, tzinfo=timezone.utc)


def test_active_accumulates(qapp) -> None:
    t = UsageTracker(work_threshold_seconds=999, idle_break_seconds=300, now=_now())
    t.tick(0, now=_now(), elapsed=20)
    t.tick(1, now=_now(), elapsed=20)
    assert t.active_seconds == 40
    assert t.today_seconds == 40


def test_idle_break_resets_streak(qapp) -> None:
    t = UsageTracker(work_threshold_seconds=999, idle_break_seconds=300, now=_now())
    t.tick(0, now=_now(), elapsed=60)
    assert t.active_seconds == 60
    # Idle beyond the break threshold -> the streak is over; away time is NOT work.
    t.tick(400, now=_now(), elapsed=20)
    assert t.active_seconds == 0
    assert t.today_seconds == 60  # unchanged: the away time didn't count


def test_below_threshold_no_nudge(qapp) -> None:
    fired: list = []
    t = UsageTracker(
        work_threshold_seconds=120, idle_break_seconds=300, cooldown_seconds=0, now=_now()
    )
    t.rest_reminder.connect(fired.append)
    t.tick(0, now=_now(), elapsed=60)  # 60 < 120
    assert fired == []


def test_at_threshold_emits_nudge_and_resets(qapp) -> None:
    fired: list = []
    t = UsageTracker(
        work_threshold_seconds=120, idle_break_seconds=300, cooldown_seconds=0, now=_now()
    )
    t.rest_reminder.connect(fired.append)
    t.tick(0, now=_now(), elapsed=120)  # exactly threshold, cooldown=0
    assert len(fired) == 1
    assert fired[0]["active_minutes"] == 2
    assert fired[0]["today_seconds"] == 120
    assert fired[0]["reminders_today"] == 1
    assert t.active_seconds == 0  # streak reset after the nudge
    assert t.reminders_today == 1


def test_cooldown_blocks_second_nudge(qapp) -> None:
    fired: list = []
    now = _now()
    t = UsageTracker(
        work_threshold_seconds=120, idle_break_seconds=300, cooldown_seconds=600, now=now
    )
    t.rest_reminder.connect(fired.append)
    t.tick(0, now=now, elapsed=120)  # first nudge fires
    assert len(fired) == 1
    # Another threshold-worth of work, but only 60s later -> still in cooldown.
    t.tick(0, now=now + timedelta(seconds=60), elapsed=120)
    assert len(fired) == 1  # suppressed by cooldown
    assert t.active_seconds == 120  # streak NOT reset; reminder didn't fire


def test_cooldown_elapsed_allows_next_nudge(qapp) -> None:
    fired: list = []
    now = _now()
    t = UsageTracker(
        work_threshold_seconds=120, idle_break_seconds=300, cooldown_seconds=600, now=now
    )
    t.rest_reminder.connect(fired.append)
    t.tick(0, now=now, elapsed=120)
    t.tick(0, now=now + timedelta(seconds=601), elapsed=120)
    assert len(fired) == 2


def test_disabled_never_emits(qapp) -> None:
    fired: list = []
    t = UsageTracker(
        work_threshold_seconds=60,
        idle_break_seconds=300,
        cooldown_seconds=0,
        enabled=False,
        now=_now(),
    )
    t.rest_reminder.connect(fired.append)
    t.tick(0, now=_now(), elapsed=120)
    assert fired == []
    # but it still counts the time
    assert t.today_seconds == 120


def test_day_rollover_resets_totals(qapp) -> None:
    now = _now()
    t = UsageTracker(work_threshold_seconds=999, idle_break_seconds=300, now=now)
    t.tick(0, now=now, elapsed=100)
    assert t.today_seconds == 100
    # next day
    next_day = now + timedelta(days=1)
    t.tick(0, now=next_day, elapsed=50)
    assert t.today_seconds == 50  # rolled over
    assert t.reminders_today == 0
    assert t.last_date == next_day.date()


def test_snapshot_roundtrip_same_day(qapp) -> None:
    now = _now()
    t = UsageTracker(work_threshold_seconds=999, idle_break_seconds=300, now=now)
    t.tick(0, now=now, elapsed=200)
    snap = t.snapshot(now)
    t2 = UsageTracker(work_threshold_seconds=999, idle_break_seconds=300, now=now)
    t2.load_snapshot(snap, now)
    assert t2.today_seconds == 200


def test_load_snapshot_ignores_other_day(qapp) -> None:
    now = _now()
    t = UsageTracker(work_threshold_seconds=999, idle_break_seconds=300, now=now)
    t.load_snapshot({"date": "2026-07-29", "today_seconds": 999, "reminders": 5}, now)
    assert t.today_seconds == 0  # stale snapshot ignored


def test_snooze_and_take_break(qapp) -> None:
    now = _now()
    t = UsageTracker(
        work_threshold_seconds=120, idle_break_seconds=300, cooldown_seconds=0, now=now
    )
    t.snooze(600, now=now)
    t.tick(0, now=now, elapsed=120)  # snoozed -> suppressed
    assert t.active_seconds == 120
    t.take_break()
    assert t.active_seconds == 0


def test_configure_changes_threshold(qapp) -> None:
    fired: list = []
    t = UsageTracker(work_threshold_seconds=999, idle_break_seconds=300, now=_now())
    t.rest_reminder.connect(fired.append)
    t.configure(work_threshold_seconds=60)
    t.tick(0, now=_now(), elapsed=60)
    assert len(fired) == 1
