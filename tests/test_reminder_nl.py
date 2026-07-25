from __future__ import annotations

import builtins
from datetime import datetime, timezone

from petgen.reminder import parse_dt
from petgen.reminder_nl import _parse_time, localnow, parse_reminder_text

# 2026-03-01 09:00 UTC is a Sunday (weekday 6)
NOW = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


def _parse(text):
    return parse_reminder_text(text, now=NOW)


def test_tomorrow_afternoon_time() -> None:
    title, trigger, rec, _ = _parse("明天下午三点 开会")
    assert title == "开会"
    assert parse_dt(trigger) == datetime(2026, 3, 2, 15, 0, tzinfo=timezone.utc)
    assert rec == "none"


def test_today_half_hour() -> None:
    _, trigger, _, _ = _parse("今天 9点半 站会")
    assert parse_dt(trigger) == datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc)


def test_weekday_next_monday() -> None:
    # now is Sunday; 周一 should be the coming Monday = 2026-03-02
    _, trigger, _, _ = _parse("周一 10点 周会")
    assert parse_dt(trigger) == datetime(2026, 3, 2, 10, 0, tzinfo=timezone.utc)


def test_evening_period() -> None:
    _, trigger, _, _ = _parse("明天晚上8点 健身")
    assert parse_dt(trigger) == datetime(2026, 3, 2, 20, 0, tzinfo=timezone.utc)


def test_recurrence_daily_splits_title() -> None:
    title, _, rec, _ = _parse("每天 喝水")
    assert rec == "daily"
    assert title == "喝水"


def test_recurrence_weekdays() -> None:
    title, _, rec, _ = _parse("工作日 写日报")
    assert rec == "weekdays"
    assert title == "写日报"


def test_recurrence_with_time() -> None:
    # 每天 9点 喝水 -> daily at 09:00; since now is 09:00, rolls to next day
    title, trigger, rec, _ = _parse("每天 9点 喝水")
    assert rec == "daily"
    assert title == "喝水"
    assert parse_dt(trigger) == datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


def test_no_time_returns_none() -> None:
    assert _parse("开会") is None
    assert _parse("") is None


def test_relative_duration_is_native_without_dateparser(monkeypatch) -> None:
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "dateparser":
            raise ImportError("dateparser intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    result = _parse("1小时后 吃药")
    assert result is not None
    title, trigger, rec, _ = result
    assert title == "吃药"
    assert rec == "none"
    assert parse_dt(trigger) == datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)


def test_relative_duration_supports_half_hour() -> None:
    title, trigger, rec, _ = _parse("半小时后 休息")
    assert title == "休息"
    assert rec == "none"
    assert parse_dt(trigger) == datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc)


# --- 12-hour period edge cases (regression: 晚上十二点 used to return noon) ---


def test_parse_time_midnight_evening_twelve() -> None:
    # 晚上12点 / 下午12点 are midnight (00:00 of the next civil day), not noon.
    assert _parse_time("晚上12点") == (0, 0)
    assert _parse_time("下午12点") == (0, 0)
    assert _parse_time("上午12点") == (0, 0)
    # And the non-12 cases still map to the 12-hour afternoon/evening band.
    assert _parse_time("晚上11点") == (23, 0)
    assert _parse_time("下午3点") == (15, 0)


def test_parse_time_rejects_out_of_range() -> None:
    # Range validation guards the recurrence / NL paths from producing a
    # minute=60 / hour=25 that would crash datetime.replace downstream.
    assert _parse_time("25点") is None
    assert _parse_time("9点60分") is None
    assert _parse_time("9点45分") == (9, 45)
    assert _parse_time("下午3点半") == (15, 30)


# --- recurrence title cleanup (regression: 每周一 9点 周会 -> "一周会") ---


def test_recurrence_strips_weekday_numeral_from_title() -> None:
    title, _, rec, _ = _parse("每周一 9点 周会")
    assert rec == "weekly"
    assert title == "周会"  # was "一周会" — weekday numeral leaked into the title

    title2, _, rec2, _ = _parse("每周三5点 站会")
    assert rec2 == "weekly"
    assert title2 == "站会"  # was "三5点 站会"


# --- timezone: local now must round-trip through UTC correctly ---


def test_parse_uses_local_now_by_default() -> None:
    # A fixed LOCAL 09:00 must produce a trigger whose LOCAL representation is
    # tomorrow 15:00 — i.e. the user's "明天下午3点" is honored in wall-clock
    # time, regardless of the machine's UTC offset.
    fixed_local = datetime(2026, 3, 1, 9, 0).astimezone()
    _, trigger, _, _ = parse_reminder_text("明天下午3点 开会", now=fixed_local)
    local = parse_dt(trigger).astimezone()
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2026, 3, 2, 15, 0)


def test_localnow_is_timezone_aware() -> None:
    # localnow() must carry a tzinfo so downstream to_iso() converts to UTC.
    assert localnow().tzinfo is not None
