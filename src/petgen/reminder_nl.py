from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from petgen.reminder import to_iso, utcnow


def localnow() -> datetime:
    """Current time in the system local zone (tz-aware).

    ``utcnow`` returns a UTC instant; this returns the same instant expressed
    in local civil time, which is what a user means by "明天下午3点". The NL
    parser builds local datetimes from this and converts to UTC at the end so
    the stored ``trigger_at`` stays canonical-UTC (what the store compares on).
    """
    return utcnow().astimezone()


_CN_DIGIT = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_WEEK = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_RECURRENCE = {
    "每天": "daily",
    "每日": "daily",
    "工作日": "weekdays",
    "每周": "weekly",
    "每月": "monthly",
}


def _num(token: str) -> int | None:
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    if all(ch in _CN_DIGIT for ch in token):
        if token == "十":
            return 10
        if token.startswith("十"):
            return 10 + _CN_DIGIT[token[1:]]
        if token.endswith("十"):
            return _CN_DIGIT[token[:-1]] * 10
        if "十" in token:
            a, b = token.split("十")
            return _CN_DIGIT[a] * 10 + _CN_DIGIT.get(b, 0)
        return _CN_DIGIT[token]
    return None


def _parse_time(s: str) -> tuple[int, int] | None:
    m = re.search(
        r"(上午|下午|晚上|早)?\s*([0-9零〇一二两三四五六七八九十]+)\s*点\s*(半|([0-9零〇一二两三四五六七八九十]+)\s*分?)?",
        s,
    )
    if not m:
        return None
    period, htok, half, mtok = m.group(1), m.group(2), m.group(3), m.group(4)
    hour = _num(htok)
    # `half` is "半" for 半 or a "<n>分" token otherwise; only "半" means 30.
    if half == "半":
        minute = 30
    elif mtok is not None:
        minute = _num(mtok)
    else:
        minute = 0
    if hour is None or minute is None:
        return None
    if hour < 0 or hour > 24 or minute < 0 or minute > 59:
        return None
    # Chinese 12-hour clock: 下午/晚上 are 12:00..23:00, with 12 itself mapping
    # to 12 (noon). 晚上12点 means midnight at the END of that evening, i.e. the
    # 0 of the NEXT day, so it maps to hour 0 (not 12). 上午12点 likewise = 0.
    if hour == 12 and period in ("下午", "晚上"):
        hour = 0  # 12 PM (zh) == 00:00 next day
    elif hour == 12 and period == "上午":
        hour = 0  # 12 AM == 00:00
    elif period in ("下午", "晚上") and hour < 12:
        hour += 12
    return hour % 24, minute


def _date_from_today(offset_days: int, now: datetime) -> datetime:
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(days=offset_days)


def _next_weekday(target: int, now: datetime) -> datetime:
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (target - now.weekday()) % 7
    if delta == 0:
        delta = 7
    return base + timedelta(days=delta)


def _parse_chinese_datetime(s: str, now: datetime) -> datetime | None:
    s = s.replace("　", " ").strip()
    date_part: datetime | None = None
    if "今天" in s:
        date_part = _date_from_today(0, now)
    elif "明天" in s:
        date_part = _date_from_today(1, now)
    elif "后天" in s:
        date_part = _date_from_today(2, now)
    else:
        mw = re.search(r"(?:下周|这周|本周)?(?:周|星期)([一二三四五六日天])", s)
        if mw:
            date_part = _next_weekday(_WEEK[mw.group(1)], now)
    if date_part is None:
        return None
    t = _parse_time(s)
    if t is None:
        # a bare date with no explicit time is not a complete trigger here; let the
        # splitter try a longer head (e.g. "今天 9点半") or a different strategy
        return None
    return date_part.replace(hour=t[0], minute=t[1], second=0, microsecond=0)


_CN_DATE_MARKERS = (
    "今天",
    "明天",
    "后天",
    "昨天",
    "周",
    "星期",
    "上午",
    "下午",
    "晚上",
    "点",
    "月",
    "日",
)


def _has_cn_date_marker(s: str) -> bool:
    return any(m in s for m in _CN_DATE_MARKERS)


def _recurrence_of(s: str) -> str | None:
    for key, value in _RECURRENCE.items():
        if key in s:
            return value
    return None


# Strip a leading recurrence marker and the weekday numeral that may follow it.
# Matches "每周一 …", "每周三 9点 …", "工作日 写日报" etc. Leaves the time token in
# place (it is stripped separately by _strip_time_token when present).
_RECURRENCE_PREFIX_RE = re.compile(
    r"^\s*(?:每天|每日|工作日|每周|每月)\s*(?:周|星期)?(?:[一二三四五六日天])?\s*"
)


def _strip_recurrence_prefix(s: str) -> str:
    return _RECURRENCE_PREFIX_RE.sub("", s).strip()


_TIME_TOKEN_RE = re.compile(
    r"(?:上午|下午|晚上|早)?\s*[0-9零〇一二两三四五六七八九十]+\s*点\s*(?:半|[0-9零〇一二两三四五六七八九十]+\s*分?)?"
)


def _strip_time_token(s: str) -> str:
    return _TIME_TOKEN_RE.sub("", s).strip()


def _fallback_parse(s: str, now: datetime) -> datetime | None:
    try:
        import dateparser
    except Exception:
        return None
    dt = dateparser.parse(
        s,
        settings={
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": now,
            "TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
        },
    )
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_relative_duration(s: str, now: datetime) -> datetime | None:
    m = re.fullmatch(
        r"\s*(半|[0-9零〇一二两三四五六七八九十]+)\s*(分钟?|分|小时|钟头|天|日|周|星期)\s*后\s*",
        s,
    )
    if not m:
        return None
    raw_amount, unit = m.group(1), m.group(2)
    amount = 0.5 if raw_amount == "半" else _num(raw_amount)
    if amount is None:
        return None
    if unit in ("分", "分钟"):
        return now + timedelta(minutes=amount)
    if unit in ("小时", "钟头"):
        return now + timedelta(hours=amount)
    if unit in ("天", "日"):
        return now + timedelta(days=amount)
    if unit in ("周", "星期"):
        return now + timedelta(weeks=amount)
    return None


def parse_reminder_text(
    text: str, now: datetime | None = None
) -> tuple[str, str, str, list[int]] | None:
    """Parse a one-line reminder into (title, trigger_iso, recurrence, custom_weekdays).

    Returns ``None`` when no time/recurrence can be understood (caller should fall
    back to a default). Chinese date/time/recurrence is handled natively; other
    relative expressions (e.g. ``1小时后``) fall back to ``dateparser`` if installed.

    ``now`` defaults to the system LOCAL time (what the user means by "明天下午3点");
    the returned ``trigger_iso`` is always canonical UTC, so callers and the store
    can compare on one timezone. Tests pass a tz-aware ``now`` to make parsing
    deterministic; passing a UTC ``now`` yields UTC-local semantics as before.
    """
    # localnow() = same instant as utcnow() but in local civil time; an explicit
    # tz-aware `now` (incl. UTC, as tests use) is respected verbatim.
    now = now or localnow()
    text = text.replace("　", " ").strip()
    if not text:
        return None

    recurrence = _recurrence_of(text)
    if recurrence:
        # Strip the recurrence prefix AND any weekday numeral that follows it
        # (每周一 / 每周三 …) so it does not leak into the title ("一周会").
        remainder = _strip_recurrence_prefix(text)
        t = _parse_time(remainder)
        if t is not None:
            base = now.replace(hour=t[0], minute=t[1], second=0, microsecond=0)
            if base <= now:
                base += timedelta(days=1)
            title = _strip_time_token(remainder)
        else:
            base = now + timedelta(hours=1)
            title = remainder
        return (title or text, to_iso(base), recurrence, [])

    parts = text.split()
    for i in range(1, min(3, len(parts)) + 1):
        head = " ".join(parts[:i])
        dt = _parse_chinese_datetime(head, now)
        if dt is None:
            dt = _parse_relative_duration(head, now)
        # Only let dateparser answer heads WITHOUT chinese date/time markers, so a
        # bare word like "今天"/"周一" (which dateparser resolves to a time-less date)
        # cannot pre-empt a longer head that carries an explicit time.
        if dt is None and not _has_cn_date_marker(head):
            dt = _fallback_parse(head, now)
        if dt is not None:
            title = " ".join(parts[i:]).strip()
            return (title or text, to_iso(dt), "none", [])

    if not _has_cn_date_marker(text):
        dt = _parse_relative_duration(text, now) or _fallback_parse(text, now)
        if dt is not None:
            return (text, to_iso(dt), "none", [])
    return None
