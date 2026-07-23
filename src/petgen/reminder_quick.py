from __future__ import annotations

from datetime import timedelta
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from petgen.reminder import to_iso, utcnow

# (text) -> (title, trigger_iso) | None  ; None = use default (+1h, full text as title)
ParseFunc = Callable[[str], tuple[str, str] | None]


class QuickCaptureDialog(QDialog):
    """Single-line quick capture. Natural-language parsing is injected (chunk 5);
    without it the whole line becomes the title, scheduled +1 hour."""

    quick_created = Signal(dict)

    def __init__(self, parser: ParseFunc | None = None, parent=None) -> None:
        super().__init__(parent)
        self._parser = parser
        self.setWindowTitle("快速新建提醒  (⌥⌘N)")
        self.resize(420, 140)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("一句话描述，例如「明天下午三点 开会」或「每天 喝水」"))
        self.input = QLineEdit()
        self.input.setPlaceholderText("提醒内容 / 自然语言时间…")
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.input)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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
