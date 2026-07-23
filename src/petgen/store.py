from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from petgen.datadir import db_path
from petgen.reminder import (
    Reminder,
    reminder_from_dict,
    reminder_to_dict,
    to_iso,
    utcnow,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pets (
  id            TEXT PRIMARY KEY,
  display_name  TEXT NOT NULL,
  dir_path      TEXT NOT NULL,
  sprite_path   TEXT NOT NULL,
  manifest_path TEXT NOT NULL,
  preview_path  TEXT,
  model         TEXT NOT NULL DEFAULT '',
  prompt        TEXT NOT NULL DEFAULT '',
  description   TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS pets_created_at_idx ON pets(created_at);
CREATE TABLE IF NOT EXISTS ai_events (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  title      TEXT NOT NULL,
  detail     TEXT,
  source     TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ai_events_created_at_idx ON ai_events(created_at);
CREATE TABLE IF NOT EXISTS reminders (
  id              TEXT PRIMARY KEY,
  title           TEXT NOT NULL,
  trigger_at      TEXT NOT NULL,
  snooze_until    TEXT,
  status          TEXT NOT NULL DEFAULT 'scheduled',
  recurrence      TEXT NOT NULL DEFAULT 'none',
  custom_weekdays TEXT NOT NULL DEFAULT '[]',
  due_handled     INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS reminders_trigger_idx ON reminders(trigger_at);
"""

# Ordered schema migrations. Index i upgrades version i -> i+1 and must be
# idempotent (a crashed upgrade may be retried). The current schema lives at
# version 1 (_migrate_v1); append new functions here when columns/tables change
# so existing on-disk databases (which only ever saw CREATE IF NOT EXISTS before)
# are upgraded instead of hitting "no such column" at runtime.
_MIGRATIONS: list = []


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


_MIGRATIONS.append(_migrate_v1)

_TARGET_VERSION = len(_MIGRATIONS)


def _connect(target: Path | sqlite3.Connection | None) -> sqlite3.Connection:
    if isinstance(target, sqlite3.Connection):
        conn = target
    else:
        path = db_path() if target is None else Path(target)
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # WAL lets the main thread (settings writes on every scale drag) and the
    # generation worker / event poller read+write concurrently without
    # "database is locked". No-op for :memory: / shared connections that
    # already configured a journal mode.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    while version < _TARGET_VERSION:
        _MIGRATIONS[version](conn)
        version += 1
        conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()


@dataclass(frozen=True)
class PetRecord:
    id: str
    display_name: str
    dir_path: str
    sprite_path: str
    manifest_path: str
    preview_path: str | None
    model: str
    prompt: str
    description: str
    created_at: str
    updated_at: str


class SettingsStore:
    """JSON-encoded key/value settings backed by the ``settings`` table."""

    def __init__(self, conn_or_path: Path | sqlite3.Connection | None = None) -> None:
        self._conn = _connect(conn_or_path)
        self._owns_conn = not isinstance(conn_or_path, sqlite3.Connection)
        _init_schema(self._conn)

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (ValueError, TypeError):
            # Corrupt / hand-edited value: degrade to the default rather than
            # crash startup (mirrors ReminderStore._to_reminder's tolerance).
            return default

    def set(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_all(self) -> dict[str, Any]:
        rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        out: dict[str, Any] = {}
        for row in rows:
            try:
                out[row["key"]] = json.loads(row["value"])
            except (ValueError, TypeError):
                continue  # skip corrupt entries instead of aborting the whole read
        return out

    def set_many(self, items: dict[str, Any]) -> None:
        self._conn.executemany(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(k, json.dumps(v, ensure_ascii=False)) for k, v in items.items()],
        )
        self._conn.commit()


class PetRegistry:
    """CRUD over the ``pets`` table (the managed pet collection index)."""

    def __init__(self, conn_or_path: Path | sqlite3.Connection | None = None) -> None:
        self._conn = _connect(conn_or_path)
        self._owns_conn = not isinstance(conn_or_path, sqlite3.Connection)
        _init_schema(self._conn)

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def register(self, record: PetRecord) -> None:
        self._conn.execute(
            "INSERT INTO pets(id, display_name, dir_path, sprite_path, manifest_path, "
            "preview_path, model, prompt, description, created_at, updated_at) "
            "VALUES (:id, :display_name, :dir_path, :sprite_path, :manifest_path, "
            ":preview_path, :model, :prompt, :description, :created_at, :updated_at) "
            "ON CONFLICT(id) DO UPDATE SET "
            "display_name=excluded.display_name, dir_path=excluded.dir_path, "
            "sprite_path=excluded.sprite_path, manifest_path=excluded.manifest_path, "
            "preview_path=excluded.preview_path, model=excluded.model, "
            "prompt=excluded.prompt, description=excluded.description, "
            "updated_at=excluded.updated_at",
            record.__dict__,
        )
        self._conn.commit()

    def list_pets(self) -> list[PetRecord]:
        rows = self._conn.execute(
            "SELECT * FROM pets ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [self._to_record(row) for row in rows]

    def get(self, pet_id: str) -> PetRecord | None:
        row = self._conn.execute(
            "SELECT * FROM pets WHERE id = ?", (pet_id,)
        ).fetchone()
        return self._to_record(row) if row else None

    def delete(self, pet_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM pets WHERE id = ?", (pet_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def rename(self, pet_id: str, display_name: str) -> bool:
        from datetime import datetime, timezone

        cursor = self._conn.execute(
            "UPDATE pets SET display_name = ?, updated_at = ? WHERE id = ?",
            (
                display_name,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                pet_id,
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM pets").fetchone()
        return int(row["n"])

    @staticmethod
    def _to_record(row: sqlite3.Row) -> PetRecord:
        return PetRecord(
            id=row["id"],
            display_name=row["display_name"],
            dir_path=row["dir_path"],
            sprite_path=row["sprite_path"],
            manifest_path=row["manifest_path"],
            preview_path=row["preview_path"],
            model=row["model"],
            prompt=row["prompt"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class AiEventStore:
    """Append-only store for events consumed from the JSONL inbox."""

    def __init__(self, conn_or_path: Path | sqlite3.Connection | None = None) -> None:
        self._conn = _connect(conn_or_path)
        self._owns_conn = not isinstance(conn_or_path, sqlite3.Connection)
        _init_schema(self._conn)

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def append(self, event: dict[str, Any]) -> bool:
        """Insert one event; returns whether it was newly inserted (dedup by id)."""
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO ai_events(id, kind, title, detail, source, created_at) "
            "VALUES (:id, :kind, :title, :detail, :source, :created_at)",
            {
                "id": event["id"],
                "kind": event["kind"],
                "title": event.get("title", ""),
                "detail": event.get("detail"),
                "source": event.get("source"),
                "created_at": event["created_at"],
            },
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def stats(self) -> dict[str, Any]:
        total = self._conn.execute("SELECT COUNT(*) AS n FROM ai_events").fetchone()["n"]
        today = self._conn.execute(
            "SELECT COUNT(*) AS n FROM ai_events WHERE created_at >= date('now')"
        ).fetchone()["n"]
        by_kind = {
            row["kind"]: row["n"]
            for row in self._conn.execute(
                "SELECT kind, COUNT(*) AS n FROM ai_events GROUP BY kind"
            ).fetchall()
        }
        return {"total": int(total), "today_count": int(today), "by_kind": by_kind}


class ReminderStore:
    """CRUD + due-detection for reminders (SQLite-backed)."""

    def __init__(self, conn_or_path: Path | sqlite3.Connection | None = None) -> None:
        self._conn = _connect(conn_or_path)
        self._owns_conn = not isinstance(conn_or_path, sqlite3.Connection)
        _init_schema(self._conn)

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()

    def upsert(self, reminder: Reminder) -> None:
        d = reminder_to_dict(reminder)
        d["custom_weekdays"] = json.dumps(d.get("custom_weekdays") or [], ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO reminders(id, title, trigger_at, snooze_until, status, recurrence, "
            "custom_weekdays, due_handled, created_at, updated_at) "
            "VALUES (:id, :title, :trigger_at, :snooze_until, :status, :recurrence, "
            ":custom_weekdays, 0, :created_at, :updated_at) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, trigger_at=excluded.trigger_at, "
            "snooze_until=excluded.snooze_until, status=excluded.status, "
            "recurrence=excluded.recurrence, custom_weekdays=excluded.custom_weekdays, "
            "updated_at=excluded.updated_at",
            d,
        )
        self._conn.commit()

    def get(self, reminder_id: str) -> Reminder | None:
        row = self._conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return self._to_reminder(row) if row else None

    def list_active(self) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status <> 'completed' ORDER BY trigger_at ASC, id ASC"
        ).fetchall()
        return [self._to_reminder(r) for r in rows]

    def list_all(self) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders ORDER BY trigger_at ASC, id ASC"
        ).fetchall()
        return [self._to_reminder(r) for r in rows]

    def delete(self, reminder_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def fetch_due(self, now: datetime | None = None) -> list[Reminder]:
        """Return not-completed, un-handled reminders whose effective time <= now,
        and mark them handled (one-shot) in the same transaction."""
        now = now or utcnow()
        now_iso = to_iso(now)
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status <> 'completed' AND due_handled = 0 "
            "AND COALESCE(NULLIF(snooze_until,''), trigger_at) <= ?",
            (now_iso,),
        ).fetchall()
        reminders = [self._to_reminder(r) for r in rows]
        if reminders:
            ids = [r.id for r in reminders]
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE reminders SET due_handled = 1, updated_at = ? WHERE id IN ({placeholders})",
                [now_iso, *ids],
            )
            self._conn.commit()
        return reminders

    def clear_handled(self, reminder_id: str) -> None:
        """Reset the handled flag so a (rolled-forward) reminder can fire again."""
        self._conn.execute(
            "UPDATE reminders SET due_handled = 0, updated_at = ? WHERE id = ?",
            (to_iso(utcnow()), reminder_id),
        )
        self._conn.commit()

    @staticmethod
    def _to_reminder(row: sqlite3.Row) -> Reminder:
        d = dict(row)
        try:
            d["custom_weekdays"] = json.loads(d.get("custom_weekdays") or "[]")
        except ValueError:
            d["custom_weekdays"] = []
        return reminder_from_dict(d)
