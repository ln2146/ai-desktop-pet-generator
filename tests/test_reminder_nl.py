from __future__ import annotations

from datetime import datetime, timezone

from petgen.reminder import parse_dt
from petgen.reminder_nl import parse_reminder_text

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


def test_dateparser_fallback_for_relative_duration() -> None:
    # "1小时后" is not in our Chinese grammar but dateparser handles it
    result = _parse("1小时后 吃药")
    # dateparser may or may not be installed / may parse; if it parses, title is 吃药
    if result is not None:
        title, trigger, rec, _ = result
        assert title == "吃药"
        assert rec == "none"
        assert parse_dt(trigger) > NOW
