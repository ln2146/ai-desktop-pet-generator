from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_DEFAULT_TIMEOUT_MS = 12_000
_LONG_TEXT_THRESHOLD = 24  # Chinese is dense; ~24 chars already wraps to multiple lines
_MAX_WIDTH = 400


class BubbleWindow(QWidget):
    """A frameless, elegant speech bubble that floats near the pet."""

    dismissed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 14)
        self._layout.setSpacing(8)

        self._label = QLabel("")
        self._label.setWordWrap(True)
        # Plain text only: bubble content can carry externally-sourced strings
        # (event titles), so never let QLabel auto-detect and render rich text.
        self._label.setTextFormat(Qt.PlainText)
        self._label.setMaximumWidth(_MAX_WIDTH - 32)
        font = QFont()
        font.setPointSize(13)
        font.setWeight(QFont.Weight.Medium)
        self._label.setFont(font)
        self._label.setStyleSheet("color: #0f172a; background: transparent; line-height: 1.4;")
        self._layout.addWidget(self._label)

        self._button_row = QHBoxLayout()
        self._button_row.setSpacing(6)
        self._close_button = QPushButton("✕")
        self._close_button.setFixedWidth(24)
        self._close_button.setFixedHeight(24)
        self._close_button.setCursor(Qt.PointingHandCursor)
        self._close_button.setStyleSheet(
            "QPushButton { border: none; background: #f1f5f9; color: #64748b; font-weight: bold; border-radius: 12px; font-size: 11px; }"
            "QPushButton:hover { background: #e2e8f0; color: #0f172a; }"
        )
        self._close_button.clicked.connect(self.hide_now)
        self._button_row.addWidget(self._close_button)
        self._button_row.addStretch(1)

        self._action_box = QHBoxLayout()
        self._action_box.setSpacing(6)
        self._button_row.addLayout(self._action_box)
        self._layout.addLayout(self._button_row)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_now)

    def show_message(
        self,
        text: str,
        *,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        actions: list[tuple[str, object]] | None = None,
        long_text: bool | None = None,
    ) -> None:
        self._label.setText(text)
        self._rebuild_actions(actions or [])
        is_long = (len(text) > _LONG_TEXT_THRESHOLD or "\n" in text) if long_text is None else long_text
        self._close_button.setVisible(bool(is_long or actions))
        self.adjustSize()
        self.show()
        self.raise_()
        self._timer.stop()
        if timeout_ms and timeout_ms > 0:
            self._timer.start(timeout_ms)

    def hide_now(self) -> None:
        self._timer.stop()
        self.hide()
        self.dismissed.emit()

    def anchor_to(self, target_global_rect: QRect) -> None:
        """Position above the pet; flip below when too close to the screen top."""
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else QRect(0, 0, 4096, 4096)
        x = target_global_rect.center().x() - self.width() // 2
        x = max(avail.left() + 4, min(x, avail.right() - self.width() - 4))
        y = target_global_rect.top() - self.height() - 12
        if y < avail.top() + 4:
            y = target_global_rect.bottom() + 12
        self.move(x, y)

    def _rebuild_actions(self, actions: list[tuple[str, object]]) -> None:
        while self._action_box.count():
            item = self._action_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for label, callback in actions:
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton { border: 1px solid #c7d2fe; background: #eef2ff; color: #4f46e5; border-radius: 12px; padding: 4px 10px; font-weight: 600; font-size: 12px; }"
                "QPushButton:hover { background: #e0e7ff; color: #4338ca; border-color: #a5b4fc; }"
            )
            button.clicked.connect(lambda _checked=False, cb=callback: self._run_action(cb))
            self._action_box.addWidget(button)

    def _run_action(self, callback: object) -> None:
        try:
            callback()  # type: ignore[misc]
        except Exception:
            pass
        self.hide_now()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(1, 1, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)

        # Subtle translucent border
        painter.setPen(QColor(226, 232, 240, 220))
        painter.setBrush(QBrush(QColor(255, 255, 255, 248)))
        painter.drawPath(path)
        painter.end()
