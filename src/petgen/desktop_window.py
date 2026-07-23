from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image

from petgen.animation import AnimationScheduler, frame_interval_ms
from petgen.overlay import BADGE_EXPRESSIONS, badge_anchor, badge_mask, composite_badge
from petgen.pet_manifest import FrameAtlas, PetManifest, load_manifest

from PySide6.QtCore import QPointF, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBitmap, QBrush, QColor, QGuiApplication, QImage, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QWidget

DRAG_THRESHOLD = 6
CORNER_MARGIN = 32
_DEFAULT_RESET_MS = {"busy": 30000}


def run(path: str | Path, *, scale: float = 1.0, passthrough: bool = True) -> int:
    """Open a floating, click-through desktop window for a generated pet (legacy)."""
    manifest = load_manifest(path)
    atlas = FrameAtlas.load(manifest.sprite_path, manifest.frame)
    app = QApplication.instance() or QApplication(["petgen-desktop"])
    window = PetWindow(manifest, atlas, scale=scale, passthrough=passthrough, interactive=False)
    window.show()
    return app.exec()


def _pil_to_qimage(image: Image.Image) -> QImage:
    rgba = image.convert("RGBA")
    qimg = QImage(
        rgba.tobytes("raw", "RGBA"),
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format_RGBA8888,
    )
    return qimg.copy()


class PetWindow(QWidget):
    pet_clicked = Signal()
    pet_context_menu_requested = Signal(QPoint)
    pet_moved = Signal(QRect)
    scale_changed = Signal(float)

    def __init__(
        self,
        manifest: PetManifest,
        atlas: FrameAtlas,
        *,
        scale: float = 1.0,
        passthrough: bool = True,
        interactive: bool = True,
        overlays: bool = True,
        motion: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._passthrough = passthrough
        self._interactive = interactive
        self._overlays = overlays
        self._motion = motion
        self._positioned = False
        self._pressed = False
        self._moved = False
        self._drag_origin = QPoint(0, 0)

        self._badge_expr: str | None = None
        self._particles: list[dict] = []
        self._breath_phase = 0.0
        self._scale = float(scale)
        self._atlas = atlas

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)

        frame = manifest.frame
        self._frame_w = max(1, round(frame.width * scale))
        self._frame_h = max(1, round(frame.height * scale))
        self.setFixedSize(self._frame_w, self._frame_h)

        self.scheduler = AnimationScheduler(
            manifest.animations, initial=manifest.initial_animation()
        )
        self._frame_qimages: dict[int, QImage] = {}
        self._base_pixmaps: dict[int, QPixmap] = {}
        self._base_bitmaps: dict[int, QBitmap] = {}
        self._badge_pixmaps: dict[tuple[int, str], QPixmap] = {}
        self._badge_regions: dict[tuple[int, str], QRegion] = {}
        self._build_frames(atlas)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(lambda: self.set_expression("idle"))
        self._particle_timer = QTimer(self)
        self._particle_timer.setInterval(30)
        self._particle_timer.timeout.connect(self._particle_tick)
        self._breath_timer = QTimer(self)
        self._breath_timer.setInterval(100)
        self._breath_timer.timeout.connect(self._breath_tick)
        if self._motion:
            self._breath_timer.start()

    # --- frames / masks -----------------------------------------------------

    def _build_frames(self, atlas: FrameAtlas) -> None:
        referenced = {
            index
            for name in self.scheduler.animation_names()
            for index in self.scheduler._animations[name].frames  # noqa: SLF001
        }
        for index in referenced:
            qimg = _pil_to_qimage(atlas.crop(index))
            self._frame_qimages[index] = qimg
            self._base_pixmaps[index] = QPixmap.fromImage(qimg)
            self._base_bitmaps[index] = QBitmap.fromImage(
                qimg.createAlphaMask().scaled(
                    self.size(), Qt.KeepAspectRatio, Qt.FastTransformation
                )
            )

    def _pix_with_badge(self, index: int, expr: str | None) -> QPixmap:
        if not expr or expr not in BADGE_EXPRESSIONS:
            return self._base_pixmaps[index]
        key = (index, expr)
        cached = self._badge_pixmaps.get(key)
        if cached is not None:
            return cached
        badged = composite_badge(self._frame_qimages[index], expr)
        pixmap = QPixmap.fromImage(badged)
        self._badge_pixmaps[key] = pixmap
        return pixmap

    def _current_pixmap(self) -> QPixmap:
        return self._pix_with_badge(self.scheduler.current_index(), self._badge_expr)

    def _mask_for(self, index: int) -> QRegion:
        region = QRegion(self._base_bitmaps[index])
        expr = self._badge_expr
        if expr and expr in BADGE_EXPRESSIONS:
            key = (index, expr)
            badge_region = self._badge_regions.get(key)
            if badge_region is None:
                badge_region = badge_mask(self.size(), expr)
                self._badge_regions[key] = badge_region
            region = region.united(badge_region)
        return region

    def _current_mask_region(self) -> QRegion:
        region = self._mask_for(self.scheduler.current_index())
        if self._particles:
            region = region.united(QRegion(QRect(0, 0, self._frame_w, self._frame_h // 2)))
        return region

    def _refresh(self) -> None:
        if self._passthrough:
            self.setMask(self._current_mask_region())
        self.update()

    # --- public API ---------------------------------------------------------

    @property
    def overlays_enabled(self) -> bool:
        return self._overlays

    def set_overlays_enabled(self, enabled: bool) -> None:
        if self._overlays == enabled:
            return
        self._overlays = enabled
        if not enabled:
            self._badge_expr = None
        self._refresh()

    @property
    def motion_enabled(self) -> bool:
        return self._motion

    def set_motion_enabled(self, enabled: bool) -> None:
        if self._motion == enabled:
            return
        self._motion = enabled
        if enabled:
            self._breath_timer.start()
            if not self._timer.isActive():
                self._timer.setInterval(frame_interval_ms(self.scheduler.current_fps))
                self._timer.start()
        else:
            self._breath_timer.stop()
            self._breath_phase = 0.0
            self._timer.stop()
        self.update()

    def set_expression(self, name: str, *, reset_after_ms: int | None = None) -> None:
        self.scheduler.play(name)
        self._reset_timer.stop()
        if self._overlays and name in BADGE_EXPRESSIONS:
            self._badge_expr = name
        else:
            self._badge_expr = None
        self._refresh()
        if not self._timer.isActive() and self._motion:
            self._timer.setInterval(frame_interval_ms(self.scheduler.current_fps))
            self._timer.start()
        delay = reset_after_ms if reset_after_ms is not None else _DEFAULT_RESET_MS.get(name)
        if delay and name != "idle":
            self._reset_timer.start(delay)

    def celebrate(self) -> None:
        colors = [(240, 96, 144), (96, 200, 240), (250, 200, 40), (120, 220, 120), (200, 120, 240)]
        for _ in range(24):
            self._particles.append(
                {
                    "x": float(self._frame_w / 2),
                    "y": float(self._frame_h * 0.22),
                    "vx": random.uniform(-2.6, 2.6),
                    "vy": random.uniform(-4.2, -1.2),
                    "life": 1.0,
                    "color": random.choice(colors),
                }
            )
        if self._passthrough:
            self.setMask(self._current_mask_region())
        if not self._particle_timer.isActive():
            self._particle_timer.start()

    def set_scale(self, scale: float, *, persist: bool = True) -> None:
        """Resize the pet in place (bottom-right corner stays put) and rebuild frames."""
        scale = max(0.5, min(3.0, float(scale)))
        if abs(scale - self._scale) < 1e-6:
            return
        self._scale = scale
        old_br = self.frameGeometry().bottomRight()
        self._frame_w = max(1, round(self._atlas._spec.width * scale))  # noqa: SLF001
        self._frame_h = max(1, round(self._atlas._spec.height * scale))  # noqa: SLF001
        self.setFixedSize(self._frame_w, self._frame_h)
        self.move(old_br.x() - self._frame_w + 1, old_br.y() - self._frame_h + 1)
        self._frame_qimages.clear()
        self._base_pixmaps.clear()
        self._base_bitmaps.clear()
        self._badge_pixmaps.clear()
        self._badge_regions.clear()
        self._build_frames(self._atlas)
        self._refresh()
        if persist:
            self.scale_changed.emit(scale)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.12 if delta > 0 else 1 / 1.12
        self.set_scale(self._scale * factor)

    # --- timers -------------------------------------------------------------

    def _tick(self) -> None:
        before = self.scheduler.current_animation
        self.scheduler.advance()
        if self.scheduler.current_animation != before:
            self._timer.setInterval(frame_interval_ms(self.scheduler.current_fps))
        self._refresh()

    def _breath_tick(self) -> None:
        self._breath_phase += 0.1
        self.update()

    def _particle_tick(self) -> None:
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.22
            p["life"] -= 0.03
        self._particles = [p for p in self._particles if p["life"] > 0]
        if not self._particles:
            self._particle_timer.stop()
            if self._passthrough:
                self.setMask(self._current_mask_region())
        self.update()

    # --- window lifecycle / painting ---------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        if not self._positioned:
            self._positioned = True
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.move(
                    geo.right() - self.width() - CORNER_MARGIN,
                    geo.bottom() - self.height() - CORNER_MARGIN,
                )
            self._refresh()
            if self._motion:
                self._timer.setInterval(frame_interval_ms(self.scheduler.current_fps))
                self._timer.start()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        for timer in (self._timer, self._reset_timer, self._particle_timer, self._breath_timer):
            timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        pixmap = self._current_pixmap()
        if self._motion and not self._particles:
            scale = 1.0 + 0.012 * math.sin(self._breath_phase)
            h = self._frame_h * scale
            target = QRectF(0, self._frame_h - h, self._frame_w, h)
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        else:
            painter.drawPixmap(self.rect(), pixmap)
        if self._particles:
            painter.setPen(Qt.NoPen)
            for p in self._particles:
                painter.setBrush(QBrush(QColor(p["color"][0], p["color"][1], p["color"][2], int(255 * p["life"]))))
                painter.drawEllipse(QPointF(p["x"], p["y"]), 3.0, 3.0)
        painter.end()

    # --- input --------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.RightButton:
            if self._interactive:
                self.pet_context_menu_requested.emit(event.globalPosition().toPoint())
            else:
                self.close()
            return
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._pressed = True
            self._moved = False

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._pressed and (event.buttons() & Qt.LeftButton):
            target = event.globalPosition().toPoint() - self._drag_origin
            if (target - self.frameGeometry().topLeft()).manhattanLength() > DRAG_THRESHOLD:
                self._moved = True
            if self._moved:
                self.move(target)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton and self._pressed:
            if not self._moved:
                self.pet_clicked.emit()
            else:
                self.pet_moved.emit(self.frameGeometry())
            self._pressed = False

    def moveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().moveEvent(event)
        if self._pressed and self._moved:
            self.pet_moved.emit(self.frameGeometry())
