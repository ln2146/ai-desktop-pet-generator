from __future__ import annotations

from datetime import timedelta
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from petgen.reminder import to_iso, utcnow
from petgen.theme import apply_theme

# (text) -> (title, trigger_iso) | None  ; None = use default (+1h, full text as title)
ParseFunc = Callable[[str], tuple[str, str] | None]


class QuickCaptureDialog(QDialog):
    """Single-line quick capture. Natural-language parsing is injected;
    without it the whole line becomes the title, scheduled +1 hour."""

    quick_created = Signal(dict)

    def __init__(self, parser: ParseFunc | None = None, parent=None) -> None:
        super().__init__(parent)
        self._parser = parser
        self.setWindowTitle("快速记提醒")
        self.resize(500, 180)
        self.setMinimumSize(460, 160)
        apply_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl = QLabel("一句话描述，例如「明天下午三点 开会」或「每天 喝水」")
        lbl.setStyleSheet("color: #475569; font-weight: 500; font-size: 13px;")
        layout.addWidget(lbl)

        self.input = QLineEdit()
        self.input.setPlaceholderText("提醒内容 / 自然语言时间…")
        self.input.setFixedHeight(38)
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.input)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = box.button(QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setText("✨ 创建")
            ok_btn.setProperty("accent", "primary")
            ok_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn = box.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setText("取消")
            cancel_btn.setCursor(Qt.PointingHandCursor)

        box.accepted.connect(self._submit)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        parsed = self._parser(text) if self._parser else None
        if parsed is not None:
            title, trigger_at = parsed
        else:
            title, trigger_at = text, to_iso(utcnow() + timedelta(hours=1))
        if not title:
            title = text
        self.quick_created.emit({"title": title, "trigger_at": trigger_at})
        self.accept()
