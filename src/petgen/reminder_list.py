from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from petgen.reminder import parse_dt

_RECURRENCE_LABEL = {
    "none": "",
    "daily": "每天",
    "weekdays": "工作日",
    "weekly": "每周",
    "monthly": "每月",
    "custom_weekly": "自定义",
}


def _format_when(iso: str) -> str:
    try:
        dt = parse_dt(iso)
        return dt.strftime("%m-%d %H:%M")
    except ValueError:
        return iso


class _ReminderCard(QFrame):
    completed = Signal(str)
    snoozed = Signal(str)
    edited = Signal(str)
    deleted = Signal(str)

    def __init__(self, reminder, parent=None) -> None:
        super().__init__(parent)
        self._id = reminder.id
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        head = QHBoxLayout()
        title = QLabel(reminder.title or "（无标题）")
        title.setStyleSheet("font-weight: 600;")
        head.addWidget(title, 1)
        recur = _RECURRENCE_LABEL.get(reminder.recurrence, "")
        if recur:
            tag = QLabel(f"🔁 {recur}")
            tag.setStyleSheet("color: #64748b;")
            head.addWidget(tag)
        when = QLabel(f"⏰ {_format_when(reminder.snooze_until or reminder.trigger_at)}")
        when.setStyleSheet("color: #64748b;")
        head.addWidget(when)
        layout.addLayout(head)

        btns = QHBoxLayout()
        done = QPushButton("完成")
        done.clicked.connect(lambda: self.completed.emit(self._id))
        snooze = QPushButton("稍后")
        snooze.clicked.connect(lambda: self.snoozed.emit(self._id))
        edit = QPushButton("编辑")
        edit.clicked.connect(lambda: self.edited.emit(self._id))
        delete = QPushButton("删除")
        delete.clicked.connect(lambda: self.deleted.emit(self._id))
        for b in (done, snooze, edit, delete):
            btns.addWidget(b)
        layout.addLayout(btns)


class ReminderListDialog(QDialog):
    new_requested = Signal()
    complete_requested = Signal(str)
    snooze_requested = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("提醒列表")
        self.resize(460, 420)
        self._cards: list[_ReminderCard] = []

        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        new_btn = QPushButton("＋ 新建提醒")
        new_btn.clicked.connect(self.new_requested.emit)
        toolbar.addWidget(new_btn)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._grid = QGridLayout(container)
        self._grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        root.addWidget(scroll)

    def refresh(self, reminders) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._cards.clear()
        if not reminders:
            empty = QLabel("还没有提醒，点「＋ 新建提醒」开始。")
            empty.setStyleSheet("color: #64748b; padding: 12px;")
            self._grid.addWidget(empty, 0, 0)
            return
        for i, reminder in enumerate(reminders):
            card = _ReminderCard(reminder)
            card.completed.connect(self.complete_requested.emit)
            card.snoozed.connect(self.snooze_requested.emit)
            card.edited.connect(self.edit_requested.emit)
            card.deleted.connect(self.delete_requested.emit)
            self._cards.append(card)
            self._grid.addWidget(card, i, 0)
