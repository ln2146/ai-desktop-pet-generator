from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from petgen.reminder import Reminder, parse_dt, to_iso

_RECURRENCE_OPTIONS = [
    ("none", "不重复"),
    ("daily", "每天"),
    ("weekdays", "工作日"),
    ("weekly", "每周"),
    ("monthly", "每月"),
    ("custom_weekly", "自定义星期…"),
]
_WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]


def _to_qdt(iso: str):
    from PySide6.QtCore import QDateTime

    dt = parse_dt(iso)
    return QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _from_qdt(qdt) -> str:
    d = qdt.date()
    t = qdt.time()
    return to_iso(datetime(d.year(), d.month(), d.day(), t.hour(), t.minute(), t.second()))


class ReminderEditorDialog(QDialog):
    """Create/edit a reminder; emits a plain dict the coordinator turns into a Reminder."""

    reminder_saved = Signal(dict)

    def __init__(self, reminder: Reminder | None = None, parent=None) -> None:
        super().__init__(parent)
        self._editing_id = reminder.id if reminder else None
        self.setWindowTitle("编辑提醒" if reminder else "新建提醒")
        self.resize(380, 320)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("提醒内容"))
        self.title = QLineEdit()
        self.title.setPlaceholderText("例如：喝水 / 开会 / 站起来活动")
        layout.addWidget(self.title)

        layout.addWidget(QLabel("提醒时间"))
        self.when = QDateTimeEdit()
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("yyyy-MM-dd  HH:mm")
        layout.addWidget(self.when)

        layout.addWidget(QLabel("重复"))
        self.recurrence = QComboBox()
        for key, label in _RECURRENCE_OPTIONS:
            self.recurrence.addItem(label, key)
        self.recurrence.currentIndexChanged.connect(self._on_recurrence_changed)
        layout.addWidget(self.recurrence)

        self._weekday_row = QHBoxLayout()
        self._weekday_boxes: list[QCheckBox] = []
        for i, label in enumerate(_WEEKDAY_LABELS):
            box = QCheckBox(label)
            box.setProperty("weekday", i)
            self._weekday_boxes.append(box)
            self._weekday_row.addWidget(box)
        self._weekday_widget = QWidget()
        self._weekday_widget.setLayout(self._weekday_row)
        self._weekday_widget.setVisible(False)
        layout.addWidget(self._weekday_widget)

        if reminder is not None:
            self._load(reminder)

        layout.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _on_recurrence_changed(self, _idx: int) -> None:
        self._weekday_widget.setVisible(self.recurrence.currentData() == "custom_weekly")

    def _load(self, reminder: Reminder) -> None:
        self.title.setText(reminder.title)
        self.when.setDateTime(_to_qdt(reminder.trigger_at))
        idx = self.recurrence.findData(reminder.recurrence)
        if idx >= 0:
            self.recurrence.setCurrentIndex(idx)
        for box in self._weekday_boxes:
            box.setChecked(box.property("weekday") in (reminder.custom_weekdays or []))
        self._on_recurrence_changed(idx)

    def _save(self) -> None:
        title = self.title.text().strip()
        if not title:
            self.title.setFocus()
            return
        data = {
            "title": title,
            "trigger_at": _from_qdt(self.when.dateTime()),
            "recurrence": self.recurrence.currentData(),
            "custom_weekdays": [
                box.property("weekday") for box in self._weekday_boxes if box.isChecked()
            ],
        }
        if self._editing_id:
            data["id"] = self._editing_id
        self.reminder_saved.emit(data)
        self.accept()
