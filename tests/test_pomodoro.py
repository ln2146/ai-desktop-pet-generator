from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.pomodoro import (  # noqa: E402
    BREAK,
    WORK,
    PomodoroService,
    PomodoroWindow,
    format_mmss,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-pomodoro"])


def test_format_mmss() -> None:
    assert format_mmss(0) == "00:00"
    assert format_mmss(65) == "01:05"
    assert format_mmss(-5) == "00:00"


def test_tick_counts_down_and_emits(qapp) -> None:
    svc = PomodoroService(work_minutes=1, break_minutes=1)
    ticks: list = []
    svc.ticked.connect(ticks.append)
    svc.start()
    svc.tick()
    assert svc.remaining == 59
    assert ticks[-1] == 59


def test_work_finish_transitions_to_break(qapp) -> None:
    svc = PomodoroService(work_minutes=1, break_minutes=1)
    finished: list = []
    phases: list = []
    svc.finished.connect(finished.append)
    svc.phase_changed.connect(phases.append)
    svc.start()
    for _ in range(60):
        svc.tick()
    assert finished == [WORK]
    assert svc.phase == BREAK
    assert svc.remaining == 60
    assert phases[-1] == BREAK


def test_break_finish_returns_to_work(qapp) -> None:
    svc = PomodoroService(work_minutes=1, break_minutes=1)
    svc.start()
    for _ in range(60):  # finish work -> break
        svc.tick()
    for _ in range(60):  # finish break -> work
        svc.tick()
    assert svc.phase == WORK


def test_pause_stops_counting(qapp) -> None:
    svc = PomodoroService(work_minutes=1, break_minutes=1)
    svc.start()
    svc.tick()
    svc.pause()
    before = svc.remaining
    svc.tick()  # no-op while paused
    assert svc.remaining == before


def test_reset_and_skip(qapp) -> None:
    svc = PomodoroService(work_minutes=1, break_minutes=1)
    svc.start()
    svc.tick()
    svc.reset()
    assert svc.phase == WORK and svc.remaining == 60 and not svc.running
    svc.skip()
    assert svc.phase == BREAK


# --- window ---------------------------------------------------------------


def test_window_start_updates_label_and_time(qapp) -> None:
    svc = PomodoroService(work_minutes=1, break_minutes=1)
    win = PomodoroWindow(svc)
    win.show()
    QApplication.processEvents()
    start_btn = win.start_btn
    QTest.mouseClick(start_btn, Qt.LeftButton, Qt.NoModifier)
    assert svc.running is True
    assert start_btn.text() == "暂停"
    svc.tick()
    assert win.time_label.text() == format_mmss(59)


def test_window_phase_change_updates_label(qapp) -> None:
    svc = PomodoroService(work_minutes=1, break_minutes=1)
    win = PomodoroWindow(svc)
    win.show()
    QApplication.processEvents()
    svc.start()
    for _ in range(60):
        svc.tick()
    QApplication.processEvents()
    assert "休息" in win.phase_label.text()
