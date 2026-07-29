from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from petgen.pomodoro import format_mmss
from petgen.usage_tracker import UsageTracker

REFRESH_INTERVAL_MS = 1000


def _format_hhmm(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


class UsagePanelDialog(QDialog):
    """Read-only view of today's computer-usage stats + rest-nudge history."""

    def __init__(
        self,
        tracker: UsageTracker,
        parent=None,
        *,
        reset_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        from petgen.theme import apply_theme

        self.tracker = tracker
        self._reset_callback = reset_callback
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self.refresh)

        self.setWindowTitle("今日使用时长")
        self.resize(360, 320)
        self.setMinimumSize(340, 300)
        self.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint
        )
        apply_theme(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # Header Title
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignCenter)
        title_row.setSpacing(6)

        title = QLabel("📊 今日使用时长")
        t_font = QFont()
        t_font.setPointSize(15)
        t_font.setBold(True)
        title.setFont(t_font)
        title.setStyleSheet("color: #0f172a; border: none;")

        title_row.addWidget(title)
        root.addLayout(title_row)

        # Hero Card (本次连续工作)
        hero_card = QFrame()
        hero_card.setStyleSheet(
            "QFrame {"
            "  background-color: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-radius: 12px;"
            "}"
        )
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(16, 12, 16, 12)
        hero_layout.setSpacing(6)
        hero_layout.setAlignment(Qt.AlignCenter)

        self.streak_label = QLabel("00:00")
        self.streak_label.setAlignment(Qt.AlignCenter)
        s_font = QFont()
        s_font.setPointSize(36)
        s_font.setBold(True)
        self.streak_label.setFont(s_font)
        self.streak_label.setStyleSheet(
            "color: #4f46e5; border: none;"
        )
        hero_layout.addWidget(self.streak_label)

        badge_row = QHBoxLayout()
        badge_row.setAlignment(Qt.AlignCenter)

        badge = QLabel("本次连续工作")
        badge.setStyleSheet(
            "background-color: #eef2ff;"
            "color: #4338ca;"
            "font-size: 11px;"
            "font-weight: 600;"
            "border-radius: 8px;"
            "padding: 2px 10px;"
            "border: none;"
        )
        badge_row.addWidget(badge)
        hero_layout.addLayout(badge_row)

        root.addWidget(hero_card)

        # Side-by-side Dashboard Cards (今日累计 & 已提醒休息)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)

        # Today Cumulative Card
        card_today = QFrame()
        card_today.setStyleSheet(
            "QFrame {"
            "  background-color: #f8fafc;"
            "  border: 1px solid #e2e8f0;"
            "  border-radius: 10px;"
            "}"
        )
        ct_layout = QVBoxLayout(card_today)
        ct_layout.setContentsMargins(10, 8, 10, 8)
        ct_layout.setSpacing(2)
        ct_layout.setAlignment(Qt.AlignCenter)

        lbl_ct_title = QLabel("⏱️ 今日累计")
        lbl_ct_title.setStyleSheet(
            "color: #64748b; font-size: 11px; font-weight: 500; border: none;"
        )
        self.today_val_lbl = QLabel("00:00")
        self.today_val_lbl.setStyleSheet(
            "color: #0f172a; font-size: 15px; font-weight: 700; border: none;"
        )
        ct_layout.addWidget(lbl_ct_title, 0, Qt.AlignCenter)
        ct_layout.addWidget(self.today_val_lbl, 0, Qt.AlignCenter)

        # Reminders Today Card
        card_remind = QFrame()
        card_remind.setStyleSheet(
            "QFrame {"
            "  background-color: #f8fafc;"
            "  border: 1px solid #e2e8f0;"
            "  border-radius: 10px;"
            "}"
        )
        cr_layout = QVBoxLayout(card_remind)
        cr_layout.setContentsMargins(10, 8, 10, 8)
        cr_layout.setSpacing(2)
        cr_layout.setAlignment(Qt.AlignCenter)

        lbl_cr_title = QLabel("☕ 提醒休息")
        lbl_cr_title.setStyleSheet(
            "color: #64748b; font-size: 11px; font-weight: 500; border: none;"
        )
        self.reminders_val_lbl = QLabel("0 次")
        self.reminders_val_lbl.setStyleSheet(
            "color: #0f172a; font-size: 15px; font-weight: 700; border: none;"
        )
        cr_layout.addWidget(lbl_cr_title, 0, Qt.AlignCenter)
        cr_layout.addWidget(self.reminders_val_lbl, 0, Qt.AlignCenter)

        stats_row.addWidget(card_today)
        stats_row.addWidget(card_remind)
        root.addLayout(stats_row)

        # Hint text note
        self.hint_note = QLabel()
        self.hint_note.setAlignment(Qt.AlignCenter)
        self.hint_note.setStyleSheet("color: #94a3b8; font-size: 11px; border: none;")
        root.addWidget(self.hint_note)

        # Detail label for backward compatibility
        self.detail_label = QLabel()
        self.detail_label.setVisible(False)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #f1f5f9;"
            "  color: #334155;"
            "  border: 1px solid #cbd5e1;"
            "  border-radius: 7px;"
            "  font-weight: 600;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #e2e8f0;"
            "  color: #0f172a;"
            "}"
        )
        refresh_btn.clicked.connect(self.refresh)

        reset_btn = QPushButton("🗑️ 重置今日统计")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setFixedHeight(32)
        reset_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #fff1f2;"
            "  color: #e11d48;"
            "  border: 1px solid #fecdd3;"
            "  border-radius: 7px;"
            "  font-weight: 600;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #ffe4e6;"
            "  border-color: #fda4af;"
            "}"
        )
        reset_btn.clicked.connect(self._reset_today)

        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(reset_btn)
        root.addLayout(btn_row)

        self.streak_hint = badge

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        self._refresh_timer.start()

    def hideEvent(self, event) -> None:
        self._refresh_timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        self.streak_label.setText(format_mmss(self.tracker.active_seconds))
        today = _format_hhmm(self.tracker.today_seconds)
        n = self.tracker.reminders_today

        self.today_val_lbl.setText(today)
        self.reminders_val_lbl.setText(f"{n} 次")
        if self.tracker.idle_detection_available:
            hint = "🌿 离开电脑超过 5 分钟会自动计为休息"
        else:
            hint = "⚠️ 未获取到系统空闲时间，当前按应用运行时间估算"
        self.hint_note.setText(hint)

        self.detail_label.setText(
            f"今日累计 {today}　·　已提醒休息 {n} 次\n"
            "（离开电脑超过 5 分钟会自动算作休息 🌿）"
        )

    def _reset_today(self) -> None:
        self.tracker.reset_today()
        if self._reset_callback is not None:
            self._reset_callback()
        self.refresh()
