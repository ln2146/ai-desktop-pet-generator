from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPushButton  # noqa: E402

from petgen.reminder import Reminder, to_iso  # noqa: E402
from petgen.reminder_editor import ReminderEditorDialog  # noqa: E402
from petgen.reminder_list import ReminderListDialog  # noqa: E402
from petgen.reminder_quick import QuickCaptureDialog  # noqa: E402

T = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-reminder-ui"])


def _btns(widget, text):
    return [b for b in widget.findChildren(QPushButton) if b.text() == text]


def _dialog_button(widget, role):
    box = widget.findChild(QDialogButtonBox)
    return box.button(role)


def _rem(rid="r1", **kw) -> Reminder:
    base = dict(id=rid, title="喝水", trigger_at="2026-03-01T09:00:00+00:00")
    base.update(kw)
    return Reminder(**base)


# --- editor ---------------------------------------------------------------


def test_editor_prefills_and_emits_on_save(qapp) -> None:
    dlg = ReminderEditorDialog(_rem(recurrence="daily"))
    dlg.show()
    QApplication.processEvents()
    saved: list = []
    dlg.reminder_saved.connect(saved.append)
    assert dlg.title.text() == "喝水"
    assert dlg.recurrence.currentData() == "daily"
    QTest.mouseClick(_dialog_button(dlg, QDialogButtonBox.Save), Qt.LeftButton, Qt.NoModifier)
    assert len(saved) == 1
    assert saved[0]["title"] == "喝水"
    assert saved[0]["recurrence"] == "daily"
    assert saved[0]["id"] == "r1"


def test_editor_empty_title_does_not_save(qapp) -> None:
    dlg = ReminderEditorDialog()
    dlg.show()
    QApplication.processEvents()
    saved: list = []
    dlg.reminder_saved.connect(saved.append)
    dlg.title.setText("   ")
    QTest.mouseClick(_dialog_button(dlg, QDialogButtonBox.Save), Qt.LeftButton, Qt.NoModifier)
    assert saved == []


def test_editor_custom_weekday_toggle_visibility(qapp) -> None:
    dlg = ReminderEditorDialog()
    dlg.show()
    QApplication.processEvents()
    assert not dlg._weekday_widget.isVisible()  # noqa: SLF001
    idx = dlg.recurrence.findData("custom_weekly")
    dlg.recurrence.setCurrentIndex(idx)
    QApplication.processEvents()
    assert dlg._weekday_widget.isVisible()  # noqa: SLF001


# --- list -----------------------------------------------------------------


def test_list_refresh_renders_cards_and_buttons(qapp) -> None:
    dlg = ReminderListDialog()
    dlg.refresh([_rem("a", title="喝水"), _rem("b", title="开会")])
    assert len(dlg._cards) == 2  # noqa: SLF001

    completed: list = []
    snoozed: list = []
    edited: list = []
    deleted: list = []
    dlg.complete_requested.connect(completed.append)
    dlg.snooze_requested.connect(snoozed.append)
    dlg.edit_requested.connect(edited.append)
    dlg.delete_requested.connect(deleted.append)

    card = dlg._cards[0]  # noqa: SLF001
    QTest.mouseClick(_btns(card, "完成")[0], Qt.LeftButton, Qt.NoModifier)
    QTest.mouseClick(_btns(card, "稍后")[0], Qt.LeftButton, Qt.NoModifier)
    QTest.mouseClick(_btns(card, "编辑")[0], Qt.LeftButton, Qt.NoModifier)
    QTest.mouseClick(_btns(card, "删除")[0], Qt.LeftButton, Qt.NoModifier)
    assert completed == ["a"] and snoozed == ["a"] and edited == ["a"] and deleted == ["a"]


def test_list_empty_state(qapp) -> None:
    dlg = ReminderListDialog()
    dlg.refresh([])
    assert dlg._cards == []  # noqa: SLF001


# --- quick capture --------------------------------------------------------


def test_quick_capture_default_plus_one_hour(qapp) -> None:
    dlg = QuickCaptureDialog()
    created: list = []
    dlg.quick_created.connect(created.append)
    dlg.input.setText("喝水")
    QTest.mouseClick(_dialog_button(dlg, QDialogButtonBox.Ok), Qt.LeftButton, Qt.NoModifier)
    assert len(created) == 1
    assert created[0]["title"] == "喝水"
    # default trigger is ~ +1h from now
    from petgen.reminder import parse_dt

    delta = parse_dt(created[0]["trigger_at"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)


def test_quick_capture_uses_injected_parser(qapp) -> None:
    def parser(text):
        return ("开会", to_iso(T("2026-03-02T15:00:00")))

    dlg = QuickCaptureDialog(parser=parser)
    created: list = []
    dlg.quick_created.connect(created.append)
    dlg.input.setText("明天下午三点 开会")
    QTest.mouseClick(_dialog_button(dlg, QDialogButtonBox.Ok), Qt.LeftButton, Qt.NoModifier)
    assert created[0] == {"title": "开会", "trigger_at": to_iso(T("2026-03-02T15:00:00"))}


def test_quick_capture_empty_does_not_emit(qapp) -> None:
    dlg = QuickCaptureDialog()
    created: list = []
    dlg.quick_created.connect(created.append)
    dlg.input.setText("   ")
    QTest.mouseClick(_dialog_button(dlg, QDialogButtonBox.Ok), Qt.LeftButton, Qt.NoModifier)
    assert created == []
