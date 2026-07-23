from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_DEFAULT_TIMEOUT_MS = 12_000
_LONG_TEXT_THRESHOLD = 60
_MAX_WIDTH = 320


class BubbleWindow(QWidget):
    """A frameless speech bubble that floats near the pet."""

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
        self._layout.setContentsMargins(14, 10, 14, 12)
        self._layout.setSpacing(6)

        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(_MAX_WIDTH - 28)
        self._label.setStyleSheet("color: #2b2b2b; background: transparent;")
        self._layout.addWidget(self._label)

        self._button_row = QHBoxLayout()
        self._button_row.setSpacing(6)
        self._close_button = QPushButton("✕")
        self._close_button.setFixedWidth(24)
        self._close_button.setStyleSheet(
            "QPushButton{border:none;color:#888;font-weight:bold;}"
            "QPushButton:hover{color:#333;}"
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
            button.setStyleSheet(
                "QPushButton{border:none;background:#eef2ff;border-radius:6px;padding:3px 8px;}"
                "QPushButton:hover{background:#dde4ff;}"
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
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 240)))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)
        painter.end()
