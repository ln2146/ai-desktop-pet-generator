from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, Qt, QTime, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from petgen.reminder import Reminder, parse_dt, to_iso
from petgen.theme import apply_theme

_RECURRENCE_OPTIONS = [
    ("none", "不重复"),
    ("daily", "每天"),
    ("weekdays", "工作日 (周一至周五)"),
    ("weekly", "每周"),
    ("monthly", "每月"),
    ("custom_weekly", "自定义"),
]
_WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]


def _to_qdt(iso: str) -> QDateTime:
    dt = parse_dt(iso).astimezone()
    return QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _from_qdt(qdt: QDateTime) -> str:
    d = qdt.date()
    t = qdt.time()
    local_dt = datetime(d.year(), d.month(), d.day(), t.hour(), t.minute(), t.second()).astimezone()
    return to_iso(local_dt)


def _from_date_time(date: QDate, time: QTime) -> str:
    local_dt = datetime(date.year(), date.month(), date.day(), time.hour(), time.minute(), time.second()).astimezone()
    return to_iso(local_dt)


class ReminderEditorDialog(QDialog):
    """Create/edit a reminder; emits a plain dict the coordinator turns into a Reminder."""

    reminder_saved = Signal(dict)

    def __init__(self, reminder: Reminder | None = None, parent=None) -> None:
        super().__init__(parent)
        self._editing_id = reminder.id if reminder else None
        self.setWindowTitle("编辑提醒" if reminder else "新建提醒")
        self.resize(540, 720)
        self.setMinimumSize(500, 680)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        apply_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        # Header
        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        head = QLabel("📝 编辑提醒事项" if reminder else "📝 新建提醒事项")
        h_font = QFont()
        h_font.setPointSize(17)
        h_font.setBold(True)
        head.setFont(h_font)
        head.setStyleSheet("color: #0f172a; border: none;")

        subhead = QLabel("自定义提醒名称、目标触发时间与循环周期")
        subhead.setStyleSheet("color: #64748b; font-size: 12px; border: none;")

        title_box.addWidget(head)
        title_box.addWidget(subhead)
        layout.addLayout(title_box)

        # Title Field
        lbl1 = QLabel("提醒内容")
        lbl1.setStyleSheet("font-weight: 600; color: #334155; font-size: 13px;")
        layout.addWidget(lbl1)
        self.title = QLineEdit()
        self.title.setPlaceholderText("例如：喝水 / 吃饭 / 开会 / 休息一下")
        self.title.setFixedHeight(38)
        layout.addWidget(self.title)

        # Date + Time Field
        lbl2 = QLabel("提醒时间")
        lbl2.setStyleSheet("font-weight: 600; color: #334155; font-size: 13px;")
        layout.addWidget(lbl2)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setMinimumDate(QDate.currentDate())
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.setFixedHeight(360)
        self.calendar.setStyleSheet(
            "QCalendarWidget { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px; }"
            "QCalendarWidget QWidget#qt_calendar_navigationbar { background: #fff7ed; border-top-left-radius: 14px; border-top-right-radius: 14px; }"
            "QCalendarWidget QToolButton { color: #c2410c; background: transparent; border: none; border-radius: 8px; padding: 4px 8px; font-weight: 700; }"
            "QCalendarWidget QToolButton:hover { background: #fed7aa; }"
            "QCalendarWidget QAbstractItemView { color: #334155; selection-background-color: #fb923c; selection-color: #ffffff; outline: 0; }"
        )
        layout.addWidget(self.calendar)

        time_row = QHBoxLayout()
        time_row.setSpacing(10)
        time_label = QLabel("具体时间")
        time_label.setStyleSheet("color: #475569; font-weight: 600; font-size: 12px;")
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFixedHeight(38)
        self.time_edit.setTime(QDateTime.currentDateTime().addSecs(1800).time())
        time_row.addWidget(time_label)
        time_row.addWidget(self.time_edit, 1)
        layout.addLayout(time_row)

        # Recurrence Field
        lbl3 = QLabel("重复模式")
        lbl3.setStyleSheet("font-weight: 600; color: #334155; font-size: 13px;")
        layout.addWidget(lbl3)
        self.recurrence = QComboBox()
        self.recurrence.setFixedHeight(38)
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
        qdt = _to_qdt(reminder.trigger_at)
        self.calendar.setSelectedDate(qdt.date())
        self.time_edit.setTime(qdt.time())
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
            "trigger_at": _from_date_time(self.calendar.selectedDate(), self.time_edit.time()),
            "recurrence": rec,
            "custom_weekdays": custom_weekdays,
        }
        if self._editing_id:
            data["id"] = self._editing_id
        self.reminder_saved.emit(data)
        self.accept()
