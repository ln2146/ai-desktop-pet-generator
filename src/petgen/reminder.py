from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

VALID_STATUS = {"scheduled", "snoozed", "completed"}
VALID_RECURRENCE = {"none", "daily", "weekdays", "weekly", "monthly", "custom_weekly"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive inputs are assumed UTC."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


@dataclass
class Reminder:
    title: str
    trigger_at: str  # ISO-8601 UTC
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    snooze_until: str | None = None
    status: str = "scheduled"
    recurrence: str = "none"
    custom_weekdays: list[int] = field(default_factory=list)  # 0=Mon .. 6=Sun
    created_at: str = field(default_factory=lambda: to_iso(utcnow()))
    updated_at: str = field(default_factory=lambda: to_iso(utcnow()))

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUS:
            raise ValueError(f"invalid status: {self.status}")
        if self.recurrence not in VALID_RECURRENCE:
            raise ValueError(f"invalid recurrence: {self.recurrence}")

    def effective_trigger_at(self) -> datetime:
        return parse_dt(self.snooze_until) if self.snooze_until else parse_dt(self.trigger_at)

    def is_due(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.status != "completed" and self.effective_trigger_at() <= now

    def next_occurrence(self, after: datetime | None = None) -> datetime | None:
        """Next trigger for a recurring reminder strictly after ``after``; None if non-recurring."""
        if self.recurrence == "none":
            return None
        after = after or parse_dt(self.trigger_at)
        base = parse_dt(self.trigger_at)
        if self.recurrence == "daily":
            cand = base + timedelta(days=1)
            while cand <= after:
                cand += timedelta(days=1)
            return cand
        if self.recurrence == "weekdays":
            cand = base + timedelta(days=1)
            while cand <= after or cand.weekday() >= 5:
                cand += timedelta(days=1)
            return cand
        if self.recurrence == "weekly":
            cand = base + timedelta(weeks=1)
            while cand <= after:
                cand += timedelta(weeks=1)
            return cand
        if self.recurrence == "monthly":
            year, month, day = base.year, base.month, base.day
            while True:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                cand = base.replace(year=year, month=month, day=_clamp_day(year, month, day))
                if cand > after:
                    return cand
        if self.recurrence == "custom_weekly":
            days = sorted({d % 7 for d in self.custom_weekdays})
            if not days:
                return None
            cand = base + timedelta(days=1)
            for _ in range(8):  # at most a week of scanning
                while cand <= after:
                    cand += timedelta(days=1)
                if cand.weekday() in days:
                    return cand
                cand += timedelta(days=1)
            return None
        return None


def _clamp_day(year: int, month: int, day: int) -> int:
    import calendar

    return min(day, calendar.monthrange(year, month)[1])


def reminder_to_dict(r: Reminder) -> dict[str, Any]:
    return asdict(r)


def reminder_from_dict(d: dict[str, Any]) -> Reminder:
    known = {f.name for f in Reminder.__dataclass_fields__.values()}
    return Reminder(**{k: v for k, v in d.items() if k in known})
