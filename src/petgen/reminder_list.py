from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
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
from petgen.theme import apply_theme

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
        self.setStyleSheet(
            "QFrame {"
            "  background-color: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-radius: 12px;"
            "}"
            "QFrame:hover { border-color: #a5b4fc; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(reminder.title or "（无标题）")
        t_font = QFont()
        t_font.setBold(True)
        t_font.setPointSize(13)
        title.setFont(t_font)
        title.setStyleSheet("color: #0f172a; border: none;")
        head.addWidget(title, 1)

        recur = _RECURRENCE_LABEL.get(reminder.recurrence, "")
        if recur:
            tag = QLabel(f"🔁 {recur}")
            tag.setStyleSheet("color: #6366f1; font-weight: 600; font-size: 11px; border: none;")
            head.addWidget(tag)

        when = QLabel(f"⏰ {_format_when(reminder.snooze_until or reminder.trigger_at)}")
        when.setStyleSheet("color: #64748b; font-size: 12px; border: none;")
        head.addWidget(when)
        layout.addLayout(head)

        btns = QHBoxLayout()
        btns.setSpacing(6)
        done = QPushButton("完成")
        done.setProperty("accent", "primary")
        done.setCursor(Qt.PointingHandCursor)
        done.setStyleSheet("QPushButton { padding: 4px 10px; font-size: 11px; }")
        done.clicked.connect(lambda: self.completed.emit(self._id))

        snooze = QPushButton("稍后")
        snooze.setCursor(Qt.PointingHandCursor)
        snooze.setStyleSheet("QPushButton { padding: 4px 10px; font-size: 11px; }")
        snooze.clicked.connect(lambda: self.snoozed.emit(self._id))

        edit = QPushButton("编辑")
        edit.setCursor(Qt.PointingHandCursor)
        edit.setStyleSheet("QPushButton { padding: 4px 10px; font-size: 11px; }")
        edit.clicked.connect(lambda: self.edited.emit(self._id))

        delete = QPushButton("删除")
        delete.setProperty("accent", "danger")
        delete.setCursor(Qt.PointingHandCursor)
        delete.setStyleSheet("QPushButton { padding: 4px 10px; font-size: 11px; }")
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
        self.setWindowTitle("提醒事项中心")
        self.resize(560, 520)
        self.setMinimumSize(480, 440)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        apply_theme(self)

        self._cards: list[_ReminderCard] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Header Title
        title_box = QHBoxLayout()
        title_text = QVBoxLayout()
        title = QLabel("📋 提醒事项中心")
        t_font = QFont()
        t_font.setPointSize(16)
        t_font.setBold(True)
        title.setFont(t_font)
        title.setStyleSheet("color: #0f172a;")

        subtitle = QLabel("查看与管理桌面宠物提醒列表")
        subtitle.setStyleSheet("color: #64748b; font-size: 12px;")
        title_text.addWidget(title)
        title_text.addWidget(subtitle)
        title_box.addLayout(title_text)
        title_box.addStretch(1)

        new_btn = QPushButton("＋ 新建提醒")
        new_btn.setProperty("accent", "primary")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setStyleSheet("QPushButton { padding: 7px 16px; font-size: 13px; }")
        new_btn.clicked.connect(self.new_requested.emit)
        title_box.addWidget(new_btn)
        root.addLayout(title_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #e2e8f0; border-radius: 12px; background: #fafafa; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(container)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def refresh(self, reminders) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._cards.clear()
        if not reminders:
            empty = QLabel("目前没有活跃的提醒事项喔 ~")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #94a3b8; font-size: 14px; padding: 40px;")
            self._grid.addWidget(empty, 0, 0)
            return

        for i, r in enumerate(reminders):
            card = _ReminderCard(r)
            card.completed.connect(self.complete_requested.emit)
            card.snoozed.connect(self.snooze_requested.emit)
            card.edited.connect(self.edit_requested.emit)
            card.deleted.connect(self.delete_requested.emit)
            self._cards.append(card)
            self._grid.addWidget(card, i, 0)
