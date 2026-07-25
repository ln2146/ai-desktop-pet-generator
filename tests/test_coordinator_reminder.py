from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.reminder import Reminder  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-coordinator-reminder"])


def _menu_texts(menu) -> list[str]:
    texts: list[str] = []
    for action in menu.actions():
        if action.text():
            texts.append(action.text())
        if action.menu() is not None:
            texts.extend(_menu_texts(action.menu()))
    return texts


class _FakeRunningWorker:
    """Stands in for a GenerationWorker that is mid-run.

    Only isRunning() is consulted by the guard, so a MagicMock with that one
    method returning True is enough to prove the re-entrancy guard fires.
    """

    def isRunning(self) -> bool:  # noqa: D401 - test stub
        return True


def test_coordinator_builds_with_reminder_and_pomodoro(qapp, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    from petgen.coordinator import AppCoordinator

    coord = AppCoordinator()
    try:
        assert coord.reminder_scheduler is not None
        assert coord.pomodoro is not None
        texts = _menu_texts(coord.tray.menu())
        for label in ["提醒列表", "番茄钟"]:
            assert label in texts
    finally:
        coord._due_timer.stop()  # noqa: SLF001


def test_coordinator_create_reminder_and_quick_capture(qapp, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    from petgen.coordinator import AppCoordinator

    coord = AppCoordinator()
    try:
        coord._open_quick_capture()  # noqa: SLF001 - wires NL parser + dialog
        assert coord.quick_capture_dialog is not None

        coord._create_reminder(  # noqa: SLF001
            {"title": "喝水", "trigger_at": "2026-03-01T09:00:00+00:00", "recurrence": "daily"}
        )
        active = coord.reminder_store.list_active()
        assert len(active) == 1 and active[0].title == "喝水" and active[0].recurrence == "daily"

        coord._open_reminder_list()  # noqa: SLF001
        assert coord.reminder_list_dialog is not None

        coord._open_pomodoro()  # noqa: SLF001
        assert coord.pomodoro_window is not None
    finally:
        coord._due_timer.stop()  # noqa: SLF001
        if coord.pomodoro_window is not None:
            coord.pomodoro_window.close()


def test_create_pet_rejects_concurrent_while_worker_running(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    """A second create request must not reassign a running QThread.

    Regression: _create_pet overwrote self._worker unconditionally, dropping the
    last Python reference to a live QThread and aborting the process. The guard
    now refuses the new request when isRunning() is True.
    """
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    from petgen.coordinator import AppCoordinator

    coord = AppCoordinator()
    try:
        coord._worker = _FakeRunningWorker()  # noqa: SLF001 - stand in for a running worker
        # If the guard works, GenerationWorker is never constructed (would need
        # network + real assets). Spy on the class to prove it.
        created: list = []
        monkeypatch.setattr(
            "petgen.coordinator.GenerationWorker",
            lambda *a, **kw: created.append(kw) or MagicMock(),
        )
        coord._create_pet("再生成一只", [])  # noqa: SLF001
        assert created == [], "a new worker was built while one was already running"
        assert coord._worker is not None and coord._worker.isRunning()  # unchanged
    finally:
        coord._due_timer.stop()  # noqa: SLF001


def test_quick_capture_and_pomodoro_dialogs_are_reused(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    """Opening twice must reuse the same widget, not orphan the first.

    Regression: each open rebuilt a fresh QDialog and dropped the prior
    reference, leaking the widget (and its signals/timers) for the session.
    """
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    from petgen.coordinator import AppCoordinator

    coord = AppCoordinator()
    try:
        coord._open_quick_capture()  # noqa: SLF001
        first_qc = coord.quick_capture_dialog
        coord._open_quick_capture()  # noqa: SLF001
        assert coord.quick_capture_dialog is first_qc  # same widget reused

        coord._open_pomodoro()  # noqa: SLF001
        first_pomo = coord.pomodoro_window
        coord._open_pomodoro()  # noqa: SLF001
        assert coord.pomodoro_window is first_pomo  # same window reused
    finally:
        coord._due_timer.stop()  # noqa: SLF001
        if coord.pomodoro_window is not None:
            coord.pomodoro_window.close()


def test_reminder_editor_does_not_leak_across_opens(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    """The editor carries per-open state, so it is rebuilt — but the previous
    dialog must be closed + scheduled for deletion rather than orphaned."""
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    from petgen.coordinator import AppCoordinator

    coord = AppCoordinator()
    try:
        coord._open_reminder_editor()  # noqa: SLF001
        first = coord.reminder_editor_dialog
        assert first is not None

        opened: list = []
        first.close = lambda: opened.append("closed")  # type: ignore[method-assign]
        # deleteLater is a real Qt method; spy via patching the bound method.
        deleted: list = []
        first.deleteLater = lambda: deleted.append("deleted")  # type: ignore[method-assign]

        coord._open_reminder_editor(  # noqa: SLF001
            Reminder(id="r1", title="喝水", trigger_at="2026-03-01T09:00:00+00:00")
        )
        # Previous dialog was closed + scheduled for deletion (no leak)…
        assert opened == ["closed"]
        assert deleted == ["deleted"]
        # …and a fresh editor took its place.
        assert coord.reminder_editor_dialog is not None
        assert coord.reminder_editor_dialog is not first
    finally:
        coord._due_timer.stop()  # noqa: SLF001
