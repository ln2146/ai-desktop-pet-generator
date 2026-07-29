from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from petgen.pomodoro import format_mmss
from petgen.usage_tracker import UsageTracker


def _format_hhmm(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


class UsagePanelDialog(QDialog):
    """Read-only view of today's computer-usage stats + rest-nudge history."""

    def __init__(self, tracker: UsageTracker, parent=None) -> None:
        super().__init__(parent)
        from petgen.theme import apply_theme

        self.tracker = tracker

        self.setWindowTitle("今日使用时长")
        self.resize(340, 220)
        self.setMinimumSize(300, 200)
        apply_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("📊 今日使用时长")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #4f46e5;")
        layout.addWidget(title)

        # Big number: current continuous streak.
        self.streak_label = QLabel(format_mmss(self.tracker.active_seconds))
        self.streak_label.setAlignment(Qt.AlignCenter)
        self.streak_label.setStyleSheet("font-size: 38px; font-weight: 700; color: #0f172a;")
        layout.addWidget(self.streak_label)

        self.streak_hint = QLabel("本次连续工作")
        self.streak_hint.setAlignment(Qt.AlignCenter)
        self.streak_hint.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.streak_hint)

        self.detail_label = QLabel()
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #334155; font-size: 13px;")
        layout.addWidget(self.detail_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        reset_btn = QPushButton("重置今日统计")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_today)
        row.addWidget(refresh_btn)
        row.addWidget(reset_btn)
        layout.addLayout(row)

    def refresh(self) -> None:
        self.streak_label.setText(format_mmss(self.tracker.active_seconds))
        today = _format_hhmm(self.tracker.today_seconds)
        n = self.tracker.reminders_today
        self.detail_label.setText(
            f"今日累计 {today}　·　已提醒休息 {n} 次\n"
            "（离开电脑超过 5 分钟会自动算作休息 🌿）"
        )

    def _reset_today(self) -> None:
        self.tracker.reset_today()
        self.refresh()
