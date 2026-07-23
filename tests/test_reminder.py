from __future__ import annotations

from datetime import datetime, timezone

import pytest

from petgen.reminder import (
    Reminder,
    parse_dt,
    reminder_from_dict,
    reminder_to_dict,
    to_iso,
)

T = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _r(**kw) -> Reminder:
    base = dict(
        id="r1",
        title="t",
        trigger_at="2026-03-01T09:00:00+00:00",
        status="scheduled",
        recurrence="none",
    )
    base.update(kw)
    return Reminder(**base)


def test_effective_trigger_uses_snooze_when_set() -> None:
    r = _r(trigger_at="2026-03-01T09:00:00+00:00", snooze_until="2026-03-01T10:30:00+00:00")
    assert r.effective_trigger_at() == T("2026-03-01T10:30:00")


def test_is_due_respects_status_and_time() -> None:
    r = _r(trigger_at="2026-03-01T09:00:00+00:00")
    assert r.is_due(T("2026-03-01T09:00:00")) is True
    assert r.is_due(T("2026-03-01T08:59:59")) is False
    r.status = "completed"
    assert r.is_due(T("2026-03-02T00:00:00")) is False


def test_next_occurrence_none_for_one_shot() -> None:
    assert _r(recurrence="none").next_occurrence() is None


def test_daily_recurrence() -> None:
    r = _r(recurrence="daily")
    assert r.next_occurrence(T("2026-03-01T09:00:00")) == T("2026-03-02T09:00:00")
    assert r.next_occurrence(T("2026-03-02T09:00:00")) == T("2026-03-03T09:00:00")


def test_weekdays_skips_weekend() -> None:
    # 2026-03-06 is Friday; next weekday occurrence after it should be Monday 2026-03-09
    r = _r(trigger_at="2026-03-06T09:00:00+00:00", recurrence="weekdays")
    assert r.next_occurrence(T("2026-03-06T09:00:00")) == T("2026-03-09T09:00:00")


def test_weekly_recurrence() -> None:
    r = _r(recurrence="weekly")
    assert r.next_occurrence(T("2026-03-01T09:00:00")) == T("2026-03-08T09:00:00")


def test_monthly_clamps_short_month() -> None:
    # Jan 31 -> next month should clamp to Feb 28 (2026 is not a leap year)
    r = _r(trigger_at="2026-01-31T09:00:00+00:00", recurrence="monthly")
    assert r.next_occurrence(T("2026-01-31T09:00:00")) == T("2026-02-28T09:00:00")
    # and then Feb 28 -> Mar 31
    nxt = r.next_occurrence(T("2026-02-28T09:00:00"))
    assert nxt == T("2026-03-31T09:00:00")


def test_custom_weekly_picks_next_listed_day() -> None:
    # 2026-03-01 is Sunday(6). Want Mon(0) and Wed(2). Next after Sun should be Mon 2026-03-02.
    r = _r(trigger_at="2026-03-01T09:00:00+00:00", recurrence="custom_weekly", custom_weekdays=[0, 2])
    nxt = r.next_occurrence(T("2026-03-01T09:00:00"))
    assert nxt == T("2026-03-02T09:00:00")
    assert nxt.weekday() == 0


def test_custom_weekly_empty_returns_none() -> None:
    r = _r(recurrence="custom_weekly", custom_weekdays=[])
    assert r.next_occurrence() is None


def test_invalid_status_or_recurrence_rejected() -> None:
    with pytest.raises(ValueError):
        _r(status="bogus")
    with pytest.raises(ValueError):
        _r(recurrence="yearly")


def test_dict_round_trip() -> None:
    r = _r(recurrence="daily", snooze_until="2026-03-01T10:00:00+00:00", custom_weekdays=[1, 3])
    d = reminder_to_dict(r)
    assert d["recurrence"] == "daily"
    r2 = reminder_from_dict(d)
    assert r2.id == r.id and r2.recurrence == "daily"
    assert r2.custom_weekdays == [1, 3]
    assert r2.snooze_until == r.snooze_until


def test_parse_and_to_iso_normalise_timezone() -> None:
    assert parse_dt("2026-03-01T09:00:00").tzinfo == timezone.utc
    assert to_iso(datetime(2026, 3, 1, 9, 0)).endswith("+00:00")
