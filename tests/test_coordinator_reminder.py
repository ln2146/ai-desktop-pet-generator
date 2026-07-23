from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


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


def test_coordinator_builds_with_reminder_and_pomodoro(qapp, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    from petgen.coordinator import AppCoordinator

    coord = AppCoordinator()
    try:
        assert coord.reminder_scheduler is not None
        assert coord.pomodoro is not None
        texts = _menu_texts(coord.tray.menu())
        for label in ["快速记提醒", "提醒列表", "番茄钟"]:
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
