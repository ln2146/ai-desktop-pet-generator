from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

WORK = "work"
BREAK = "break"


def format_mmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class PomodoroService(QObject):
    """25/5 focus timer. Timer-driven in the app; tests call :meth:`tick` directly."""

    phase_changed = Signal(str)  # WORK / BREAK
    finished = Signal(str)  # the phase that just finished
    ticked = Signal(int)  # remaining seconds

    def __init__(
        self,
        work_minutes: int = 25,
        break_minutes: int = 5,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.work_seconds = max(1, work_minutes) * 60
        self.break_seconds = max(1, break_minutes) * 60
        self.phase = WORK
        self.remaining = self.work_seconds
        self.running = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.tick)

    # --- controls -----------------------------------------------------------

    def start(self) -> None:
        self.running = True
        self._timer.start()
        self.ticked.emit(self.remaining)

    def pause(self) -> None:
        self.running = False
        self._timer.stop()

    def toggle(self) -> None:
        if self.running:
            self.pause()
        else:
            self.start()

    def reset(self) -> None:
        self.pause()
        self.phase = WORK
        self.remaining = self.work_seconds
        self.phase_changed.emit(self.phase)
        self.ticked.emit(self.remaining)

    def skip(self) -> None:
        self._enter(BREAK if self.phase == WORK else WORK, announce=False)

    # --- ticking ------------------------------------------------------------

    def tick(self) -> None:
        if not self.running:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            done = self.phase
            self.finished.emit(done)
            self._enter(BREAK if done == WORK else WORK, announce=True)
        else:
            self.ticked.emit(self.remaining)

    def _enter(self, phase: str, *, announce: bool) -> None:
        self.phase = phase
        self.remaining = self.work_seconds if phase == WORK else self.break_seconds
        self.phase_changed.emit(phase)
        self.ticked.emit(self.remaining)


_PHASE_TEXT = {WORK: "🍅 专注中", BREAK: "☕ 休息中"}


class PomodoroWindow(QDialog):
    def __init__(self, service: PomodoroService | None = None, parent=None) -> None:
        super().__init__(parent)
        from petgen.theme import apply_theme

        self.setWindowTitle("番茄钟助手")
        self.resize(320, 200)
        self.setMinimumSize(280, 180)
        apply_theme(self)

        self.service = service or PomodoroService()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.phase_label = QLabel(_PHASE_TEXT[self.service.phase])
        self.phase_label.setAlignment(Qt.AlignCenter)
        self.phase_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #4f46e5;")
        layout.addWidget(self.phase_label)

        self.time_label = QLabel(format_mmss(self.service.remaining))
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 38px; font-weight: 700; color: #0f172a;")
        layout.addWidget(self.time_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.start_btn = QPushButton("开始")
        self.start_btn.setProperty("accent", "primary")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._toggle)

        reset_btn = QPushButton("重置")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self.service.reset)

        skip_btn = QPushButton("跳过")
        skip_btn.setCursor(Qt.PointingHandCursor)
        skip_btn.clicked.connect(self.service.skip)

        for b in (self.start_btn, reset_btn, skip_btn):
            row.addWidget(b)
        layout.addLayout(row)

        self.service.phase_changed.connect(self._on_phase)
        self.service.ticked.connect(self._on_tick)

    def _toggle(self) -> None:
        self.service.toggle()
        self.start_btn.setText("暂停" if self.service.running else "开始")

    def _on_phase(self, phase: str) -> None:
        self.phase_label.setText(_PHASE_TEXT.get(phase, phase))
        self.time_label.setText(format_mmss(self.service.remaining))

    def _on_tick(self, remaining: int) -> None:
        self.time_label.setText(format_mmss(remaining))
