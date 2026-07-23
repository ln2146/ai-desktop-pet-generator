from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # QRect is imported lazily inside badge_anchor to avoid a hard Qt dep
    from PySide6.QtCore import QRect

BADGE_EXPRESSIONS = {"happy", "busy", "alert", "error"}
BADGE_SIZE = 30


def badge_anchor(frame_size) -> "QRect":
    """Top-right free space inside a generated frame (the pet is centered)."""
    from PySide6.QtCore import QRect

    return QRect(frame_size.width() - BADGE_SIZE - 6, 6, BADGE_SIZE, BADGE_SIZE)


def badge_mask(frame_size, expression: str):
    """Input region for a badge so it stays clickable under setMask."""
    from PySide6.QtGui import QRegion

    if expression not in BADGE_EXPRESSIONS:
        return QRegion()
    return QRegion(badge_anchor(frame_size))


def composite_badge(frame, expression: str):
    """Return a copy of ``frame`` (QImage) with the expression badge drawn on."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter

    out = frame.copy()
    if expression not in BADGE_EXPRESSIONS:
        return out
    painter = QPainter(out)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        draw_badge(painter, expression, QRectF(badge_anchor(frame.size())))
    finally:
        painter.end()
    return out


def draw_badge(painter, expression: str, rect) -> None:
    """Vector badge glyphs drawn with QPainter (no icon dependency)."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QBrush, QColor, QPainter, QPen

    if expression not in BADGE_EXPRESSIONS:
        return
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    cx = rect.center().x()
    cy = rect.center().y()
    r = min(rect.width(), rect.height()) / 2.0
    if expression == "happy":
        _draw_hearts(painter, rect)
    elif expression == "busy":
        _draw_gear(painter, cx, cy, r)
    elif expression == "alert":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(232, 64, 64)))
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.setPen(QPen(QColor(255, 255, 255), max(1.0, r * 0.18)))
        painter.drawLine(QPointF(cx, cy - r * 0.45), QPointF(cx, cy + r * 0.1))
        painter.drawPoint(QPointF(cx, cy + r * 0.45))
    elif expression == "error":
        _draw_star(painter, cx, cy, r, rotation=math.radians(12))
    painter.restore()


def _draw_hearts(painter, rect) -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QBrush, QColor, QPainterPath

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(240, 96, 144)))
    offsets = [(0.30, 0.32, 0.42), (0.66, 0.30, 0.34), (0.50, 0.62, 0.40)]
    for fx, fy, fs in offsets:
        w = rect.width() * fs
        h = rect.height() * fs
        box = QRectF(rect.x() + rect.width() * fx - w / 2, rect.y() + rect.height() * fy - h / 2, w, h)
        path = QPainterPath()
        path.moveTo(box.center().x(), box.bottom())
        path.cubicTo(
            box.left() - w * 0.1, box.top() + h * 0.2,
            box.left() + w * 0.2, box.top() - h * 0.1,
            box.center().x(), box.top() + h * 0.35,
        )
        path.cubicTo(
            box.right() - w * 0.2, box.top() - h * 0.1,
            box.right() + w * 0.1, box.top() + h * 0.2,
            box.center().x(), box.bottom(),
        )
        painter.drawPath(path)


def _draw_gear(painter, cx: float, cy: float, r: float) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QBrush, QColor, QPainterPath

    teeth = 8
    path = QPainterPath()
    for i in range(teeth * 2):
        ang = math.pi * i / teeth
        rad = r if i % 2 == 0 else r * 0.72
        p = QPointF(cx + rad * math.cos(ang), cy + rad * math.sin(ang))
        if i == 0:
            path.moveTo(p)
        else:
            path.lineTo(p)
    path.closeSubpath()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(150, 150, 160)))
    painter.drawPath(path)
    painter.setBrush(QBrush(QColor(235, 235, 240)))
    painter.drawEllipse(QPointF(cx, cy), r * 0.32, r * 0.32)


def _draw_star(painter, cx: float, cy: float, r: float, rotation: float = 0.0) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QBrush, QColor, QPen

    points = 5
    path_pts = []
    for i in range(points * 2):
        ang = rotation - math.pi / 2 + math.pi * i / points
        rad = r if i % 2 == 0 else r * 0.45
        path_pts.append(QPointF(cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.moveTo(path_pts[0])
    for p in path_pts[1:]:
        path.lineTo(p)
    path.closeSubpath()
    painter.setPen(QPen(QColor(200, 150, 0), max(1.0, r * 0.08)))
    painter.setBrush(QBrush(QColor(250, 200, 40)))
    painter.drawPath(path)
