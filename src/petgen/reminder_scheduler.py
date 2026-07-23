from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

from petgen.reminder import Reminder, to_iso, utcnow
from petgen.store import ReminderStore

DEFAULT_SNOOZE_MINUTES = 15


class ReminderScheduler(QObject):
    """Reminder lifecycle + due detection on top of ``ReminderStore``.

    The coordinator owns the polling timer and calls :meth:`check_due`; this class
    only mutates state and emits signals, so it is fully unit-testable without timers.
    """

    reminder_due = Signal(object)  # Reminder
    reminder_completed = Signal(object)  # Reminder
    reminders_changed = Signal()

    def __init__(self, store: ReminderStore, parent=None) -> None:
        super().__init__(parent)
        self._store = store

    # --- mutations ----------------------------------------------------------

    def create(
        self,
        title: str,
        trigger_at: datetime | str,
        *,
        recurrence: str = "none",
        custom_weekdays: list[int] | None = None,
    ) -> Reminder:
        if isinstance(trigger_at, datetime):
            trigger_at = to_iso(trigger_at)
        reminder = Reminder(
            title=title,
            trigger_at=trigger_at,
            recurrence=recurrence,
            custom_weekdays=list(custom_weekdays or []),
        )
        self._store.upsert(reminder)
        self.reminders_changed.emit()
        return reminder

    def complete(self, reminder_id: str) -> Reminder | None:
        reminder = self._store.get(reminder_id)
        if reminder is None:
            return None
        if reminder.recurrence != "none":
            nxt = reminder.next_occurrence()
            if nxt is not None:
                reminder.trigger_at = to_iso(nxt)
                reminder.snooze_until = None
                reminder.status = "scheduled"
                self._store.upsert(reminder)
                self._store.clear_handled(reminder_id)
                self.reminders_changed.emit()
                return reminder
        reminder.status = "completed"
        reminder.updated_at = to_iso(utcnow())
        self._store.upsert(reminder)
        self.reminder_completed.emit(reminder)
        self.reminders_changed.emit()
        return reminder

    def update(
        self,
        reminder_id: str,
        *,
        title: str,
        trigger_at: datetime | str,
        recurrence: str = "none",
        custom_weekdays: list[int] | None = None,
    ) -> Reminder | None:
        """Edit an existing reminder's schedule; returns None if it is gone.

        Centralises the edit path (previously duplicated in the coordinator):
        mutate the fields, persist, reset the handled flag so the new trigger
        time can fire, and notify listeners.
        """
        reminder = self._store.get(reminder_id)
        if reminder is None:
            return None
        if isinstance(trigger_at, datetime):
            trigger_at = to_iso(trigger_at)
        reminder.title = title
        reminder.trigger_at = trigger_at
        reminder.recurrence = recurrence
        reminder.custom_weekdays = list(custom_weekdays or [])
        reminder.updated_at = to_iso(utcnow())
        self._store.upsert(reminder)
        self._store.clear_handled(reminder_id)
        self.reminders_changed.emit()
        return reminder

    def snooze(
        self,
        reminder_id: str,
        minutes: int = DEFAULT_SNOOZE_MINUTES,
        *,
        now: datetime | None = None,
    ) -> Reminder | None:
        reminder = self._store.get(reminder_id)
        if reminder is None:
            return None
        now = now or utcnow()
        base = max(now, reminder.effective_trigger_at())
        reminder.snooze_until = to_iso(base + timedelta(minutes=minutes))
        reminder.status = "snoozed"
        reminder.updated_at = to_iso(utcnow())
        self._store.upsert(reminder)
        self._store.clear_handled(reminder_id)
        self.reminders_changed.emit()
        return reminder

    def delete(self, reminder_id: str) -> bool:
        deleted = self._store.delete(reminder_id)
        if deleted:
            self.reminders_changed.emit()
        return deleted

    # --- due detection ------------------------------------------------------

    def check_due(self, now: datetime | None = None) -> list[Reminder]:
        due = self._store.fetch_due(now)
        for reminder in due:
            self.reminder_due.emit(reminder)
        return due
