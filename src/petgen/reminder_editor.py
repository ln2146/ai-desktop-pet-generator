from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
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
from petgen.theme import apply_theme

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
        self.resize(480, 420)
        self.setMinimumSize(440, 360)
        apply_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        # Header
        head = QLabel("编辑提醒事项" if reminder else "新建提醒事项")
        h_font = QFont()
        h_font.setPointSize(15)
        h_font.setBold(True)
        head.setFont(h_font)
        layout.addWidget(head)

        # Title Field
        lbl1 = QLabel("提醒内容")
        lbl1.setStyleSheet("font-weight: 600; color: #334155;")
        layout.addWidget(lbl1)
        self.title = QLineEdit()
        self.title.setPlaceholderText("例如：喝水 / 开会 / 站起来活动")
        self.title.setFixedHeight(36)
        layout.addWidget(self.title)

        # DateTime Field
        lbl2 = QLabel("提醒时间")
        lbl2.setStyleSheet("font-weight: 600; color: #334155;")
        layout.addWidget(lbl2)
        self.when = QDateTimeEdit()
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("yyyy-MM-dd  HH:mm")
        self.when.setFixedHeight(36)
        layout.addWidget(self.when)

        # Recurrence Field
        lbl3 = QLabel("重复模式")
        lbl3.setStyleSheet("font-weight: 600; color: #334155;")
        layout.addWidget(lbl3)
        self.recurrence = QComboBox()
        self.recurrence.setFixedHeight(36)
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
        save_btn = box.button(QDialogButtonBox.Save)
        if save_btn:
            save_btn.setText("保存")
            save_btn.setProperty("accent", "primary")
            save_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn = box.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setText("取消")
            cancel_btn.setCursor(Qt.PointingHandCursor)

        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _on_recurrence_changed(self, _idx: int) -> None:
        self._weekday_widget.setVisible(self.recurrence.currentData() == "custom_weekly")

    def _load(self, reminder: Reminder) -> None:
        self.title.setText(reminder.title)
        self.when.setDateTime(_to_qdt(reminder.trigger_at))
        rec = reminder.recurrence or "none"
        idx = self.recurrence.findData(rec)
        if idx >= 0:
            self.recurrence.setCurrentIndex(idx)
        if rec == "custom_weekly":
            for box in self._weekday_boxes:
                w = int(box.property("weekday"))
                box.setChecked(w in (reminder.custom_weekdays or []))

    def _save(self) -> None:
        title = self.title.text().strip()
        if not title:
            return
        rec = str(self.recurrence.currentData())
        custom_weekdays: list[int] = []
        if rec == "custom_weekly":
            custom_weekdays = [
                int(box.property("weekday"))
                for box in self._weekday_boxes
                if box.isChecked()
            ]
        data = {
            "title": title,
            "trigger_at": _from_qdt(self.when.dateTime()),
            "recurrence": rec,
            "custom_weekdays": custom_weekdays,
        }
        if self._editing_id:
            data["id"] = self._editing_id
        self.reminder_saved.emit(data)
        self.accept()
