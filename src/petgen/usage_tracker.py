"""Tracks continuous computer usage and nudges the user to rest.

Like :mod:`petgen.pomodoro` and :mod:`petgen.reminder_scheduler`, this service is
a pure state machine that emits signals and holds NO QTimer -- the coordinator
owns the polling timer and calls :meth:`UsageTracker.tick`, which keeps the whole
thing unit-testable without timers.

Time model:

* "active" = the user is at the machine. The coordinator samples the OS idle
  time (see :mod:`petgen.idle_time`) and, when the user has been idle long
  enough (``idle_break_seconds``), we treat the streak as broken: the current
  ``active_seconds`` resets to 0 (the person went to rest).
* ``today_seconds`` accumulates active time across streaks within the same day,
  and resets on day rollover.
* When ``active_seconds`` crosses ``work_threshold_seconds`` and the cooldown
  since the last nudge has elapsed, we emit :attr:`rest_reminder` and reset the
  streak so the user isn't nagged again until they've worked another threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

from petgen.reminder import utcnow

# Eye-care defaults: nudge after 45min of continuous use, treat 5min away as a
# proper break, and don't nag more often than every 15min.
DEFAULT_WORK_THRESHOLD_SECONDS = 45 * 60
DEFAULT_IDLE_BREAK_SECONDS = 5 * 60
DEFAULT_COOLDOWN_SECONDS = 15 * 60

SNAPSHOT_KEY = "usage.snapshot"


def _local_date(now: datetime):
    if now.tzinfo is None or now.utcoffset() is None:
        return now.date()
    return now.astimezone().date()


@dataclass
class _Config:
    work_threshold_seconds: int = DEFAULT_WORK_THRESHOLD_SECONDS
    idle_break_seconds: int = DEFAULT_IDLE_BREAK_SECONDS
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS
    enabled: bool = True


class UsageTracker(QObject):
    """Continuous-usage state machine; timer owned by the coordinator."""

    # Emitted when a rest nudge fires. Payload is a snapshot dict so the bubble
    # handler doesn't need to reach back into tracker internals.
    rest_reminder = Signal(object)  # dict: {active_minutes, today_seconds, reminders_today}

    def __init__(
        self,
        *,
        work_threshold_seconds: int = DEFAULT_WORK_THRESHOLD_SECONDS,
        idle_break_seconds: int = DEFAULT_IDLE_BREAK_SECONDS,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        enabled: bool = True,
        now: datetime | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._cfg = _Config(
            work_threshold_seconds=max(1, work_threshold_seconds),
            idle_break_seconds=max(1, idle_break_seconds),
            cooldown_seconds=max(0, cooldown_seconds),
            enabled=enabled,
        )
        now = now or utcnow()
        self.last_date = _local_date(now)
        self.today_seconds = 0
        self.active_seconds = 0
        self.reminders_today = 0
        self.idle_detection_available = True
        self.last_reminder_at: datetime = now - timedelta(seconds=self._cfg.cooldown_seconds + 1)

    # --- configuration ------------------------------------------------------

    def configure(
        self,
        *,
        work_threshold_seconds: int | None = None,
        idle_break_seconds: int | None = None,
        cooldown_seconds: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        if work_threshold_seconds is not None:
            self._cfg.work_threshold_seconds = max(1, work_threshold_seconds)
        if idle_break_seconds is not None:
            self._cfg.idle_break_seconds = max(1, idle_break_seconds)
        if cooldown_seconds is not None:
            self._cfg.cooldown_seconds = max(0, cooldown_seconds)
        if enabled is not None:
            self._cfg.enabled = enabled

    # --- the main advance ---------------------------------------------------

    def tick(
        self,
        idle_seconds: float | None,
        now: datetime | None = None,
        *,
        elapsed: int,
    ) -> None:
        """Advance the state machine by ``elapsed`` seconds.

        ``idle_seconds`` is the OS-reported idle. When it is unavailable
        (``None``), we mark :attr:`idle_detection_available` false and rely on
        ``elapsed`` so callers can surface the degraded estimate explicitly.
        ``elapsed`` must be supplied by the caller (the coordinator truncates it
        to avoid sleep gaps inflating the count).
        """
        now = now or utcnow()
        self._rollover_day_if_needed(now)

        self.idle_detection_available = idle_seconds is not None
        on_break = idle_seconds is not None and idle_seconds >= self._cfg.idle_break_seconds
        if on_break:
            # The user stepped away long enough to count as a rest: the streak
            # is over. We don't credit the away time to today_seconds (it wasn't
            # work), and don't carry the stale streak forward.
            self.active_seconds = 0
            return

        elapsed = max(0, int(elapsed))
        self.active_seconds += elapsed
        self.today_seconds += elapsed

        if (
            self._cfg.enabled
            and self.active_seconds >= self._cfg.work_threshold_seconds
            and (now - self.last_reminder_at).total_seconds() >= self._cfg.cooldown_seconds
        ):
            self.last_reminder_at = now
            self.reminders_today += 1
            active_minutes = self.active_seconds // 60
            self.active_seconds = 0
            self.rest_reminder.emit(
                {
                    "active_minutes": active_minutes,
                    "today_seconds": self.today_seconds,
                    "reminders_today": self.reminders_today,
                }
            )

    # --- snooze / reset -----------------------------------------------------

    def snooze(self, seconds: int, now: datetime | None = None) -> None:
        """Postpone the next nudge by ``seconds`` (pushes the cooldown forward)."""
        now = now or utcnow()
        self.last_reminder_at = now + timedelta(seconds=max(0, seconds - self._cfg.cooldown_seconds))

    def take_break(self) -> None:
        """User accepted the nudge: end the streak now (no more nudge until threshold)."""
        self.active_seconds = 0

    def reset_today(self, now: datetime | None = None) -> None:
        now = now or utcnow()
        self.last_date = _local_date(now)
        self.today_seconds = 0
        self.reminders_today = 0

    # --- internals ----------------------------------------------------------

    def _rollover_day_if_needed(self, now: datetime) -> None:
        local_date = _local_date(now)
        if local_date != self.last_date:
            self.last_date = local_date
            self.today_seconds = 0
            self.reminders_today = 0

    # --- persistence --------------------------------------------------------

    def snapshot(self, now: datetime | None = None) -> dict:
        now = now or utcnow()
        return {
            "date": _local_date(now).isoformat(),
            "today_seconds": self.today_seconds,
            "reminders": self.reminders_today,
        }

    def load_snapshot(self, data: dict | None, now: datetime | None = None) -> None:
        """Restore today's totals from a stored snapshot.

        ``active_seconds`` is intentionally NOT persisted (the streak restarts
        after relaunch, same trade-off as the pomodoro timer). A snapshot from a
        prior day is ignored, leaving a clean slate for today.
        """
        if not data:
            return
        now = now or utcnow()
        try:
            snap_date_str = data.get("date")
            local_date = _local_date(now)
            if snap_date_str and snap_date_str != local_date.isoformat():
                return  # stale snapshot from another day; keep the fresh state
            self.today_seconds = max(0, int(data.get("today_seconds", 0)))
            self.reminders_today = max(0, int(data.get("reminders", 0)))
            self.last_date = local_date
        except (TypeError, ValueError):
            return  # corrupt snapshot: degrade silently to defaults
