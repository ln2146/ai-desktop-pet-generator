from __future__ import annotations

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBitmap,
    QBrush,
    QColor,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

# macOS pins menu-bar (status item) icons to the bar thickness (~22-24pt); a
# larger image is scaled back down by the OS, so this is the logical height we
# aim to fill. We still render at physical = target * devicePixelRatio so the
# icon stays crisp on retina displays instead of being upscaled and blurry.
_TRAY_ICON_TARGET_PT = 24


def _placeholder_icon(size: int = 22) -> QIcon:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(120, 130, 150)))
    cx = cy = size / 2
    painter.drawEllipse(int(cx - size * 0.22), int(cy - size * 0.12), int(size * 0.44), int(size * 0.4))
    for fx, fy in [(0.3, 0.28), (0.5, 0.22), (0.7, 0.28), (0.22, 0.5)]:
        painter.drawEllipse(int(size * fx - 2), int(size * fy - 2), 4, 4)
    painter.end()
    return QIcon(QPixmap.fromImage(image))


def _make_tray_icon(pixmap: QPixmap, target_pt: int = _TRAY_ICON_TARGET_PT) -> QIcon:
    """Build a crisp, menu-bar-filling icon from a (transparent) preview image.

    The preview already hugs the pet with a few px of padding; we tighten to the
    opaque bounds so the pet fills the slot, render at the screen's pixel ratio
    so it is not blurry on retina, and paint a thin white outline that keeps the
    silhouette readable against any colour showing through the translucent bar.
    """
    screen = QGuiApplication.primaryScreen()
    dpr = max(1.0, float(screen.devicePixelRatio())) if screen is not None else 2.0
    phys = max(1, int(round(target_pt * dpr)))

    img = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
    bbox = QRegion(QBitmap.fromImage(img.createAlphaMask())).boundingRect()
    bbox = bbox.intersected(img.rect())
    if bbox.isValid() and bbox.width() > 0 and bbox.height() > 0:
        img = img.copy(bbox)

    outline = max(1, int(round(dpr)))  # white border thickness, ~1 logical px
    draw_side = max(1, phys - 2 * outline)
    main = (
        QPixmap.fromImage(img)
        .scaled(draw_side, draw_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        .toImage()
        .convertToFormat(QImage.Format_ARGB32)
    )

    # white silhouette: same alpha as the pet, solid white rgb
    white = QImage(main.size(), QImage.Format_ARGB32)
    white.fill(Qt.transparent)
    wp = QPainter(white)
    wp.setCompositionMode(QPainter.CompositionMode_Source)
    wp.fillRect(white.rect(), QColor(255, 255, 255, 235))
    wp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    wp.drawImage(0, 0, main)
    wp.end()

    canvas = QImage(phys, phys, QImage.Format_ARGB32)
    canvas.fill(Qt.transparent)
    cp = QPainter(canvas)
    cp.setRenderHint(QPainter.SmoothPixmapTransform, True)
    mw, mh = main.width(), main.height()
    base = QRect((phys - mw) // 2, (phys - mh) // 2, mw, mh)
    for r in range(1, outline + 1):  # solid white outline hugging the pet
        for dx in (-r, 0, r):
            for dy in (-r, 0, r):
                if dx == 0 and dy == 0:
                    continue
                cp.drawImage(base.translated(dx, dy), white)
    cp.drawImage(base, main)
    cp.end()

    out = QPixmap.fromImage(canvas)
    out.setDevicePixelRatio(dpr)
    return QIcon(out)


class TrayController(QObject):
    show_pet_requested = Signal()
    library_requested = Signal()
    settings_requested = Signal()
    about_requested = Signal()
    character_selected = Signal(str)
    quiet_toggled = Signal(bool)
    quick_capture_requested = Signal()
    reminder_list_requested = Signal()
    pomodoro_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._available = QSystemTrayIcon.isSystemTrayAvailable()
        self._tray = QSystemTrayIcon(self) if self._available else None
        self._show_action: QAction | None = None
        self._quiet_action: QAction | None = None
        self._character_menu: QMenu | None = None
        self._character_actions: list[QAction] = []
        self._menu = self._build_menu()
        if self._tray is not None:
            self._tray.setContextMenu(self._menu)
            self._tray.setIcon(_placeholder_icon())
            self._tray.setToolTip("PetGen 桌宠")
            self._tray.activated.connect(self._on_activated)

    # --- public API ---------------------------------------------------------

    def menu(self) -> QMenu:
        return self._menu

    def character_menu(self) -> QMenu | None:
        return self._character_menu

    def is_available(self) -> bool:
        return self._available

    def show(self) -> None:
        if self._tray is not None:
            self._tray.show()

    def set_icon_from_preview(self, path: str | None) -> None:
        if self._tray is None:
            return
        icon = None
        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                icon = _make_tray_icon(pixmap)
        self._tray.setIcon(icon or _placeholder_icon())

    def set_pet_visible(self, visible: bool) -> None:
        if self._show_action is not None:
            self._show_action.setChecked(visible)

    def set_quiet(self, quiet: bool) -> None:
        if self._quiet_action is not None:
            self._quiet_action.setChecked(quiet)

    def set_characters(self, pets, selected_id: str | None) -> None:
        if self._character_menu is None:
            return
        for action in self._character_actions:
            self._character_menu.removeAction(action)
        self._character_actions.clear()
        if not pets:
            empty = self._character_menu.addAction("（还没有宠物，去创建一个吧）")
            empty.setEnabled(False)
            self._character_actions.append(empty)
            return
        for record in pets:
            action = self._character_menu.addAction(record.display_name or record.id)
            action.setCheckable(True)
            action.setChecked(record.id == selected_id)
            pid = record.id
            action.triggered.connect(lambda _checked=False, pet_id=pid: self.character_selected.emit(pet_id))
            self._character_actions.append(action)

    # --- menu construction --------------------------------------------------

    def _build_menu(self) -> QMenu:
        from petgen.theme import apply_theme

        menu = QMenu()
        apply_theme(menu)
        self._show_action = menu.addAction("显示宠物")
        self._show_action.setCheckable(True)
        self._show_action.setChecked(True)
        self._show_action.triggered.connect(lambda checked: self.show_pet_requested.emit())
        menu.addAction("宠物中心…").triggered.connect(lambda: self.library_requested.emit())
        self._character_menu = QMenu("切换角色")  # kept for attribute compatibility
        apply_theme(self._character_menu)
        menu.addSeparator()
        menu.addAction("＋ 快速记提醒").triggered.connect(lambda: self.quick_capture_requested.emit())
        menu.addAction("提醒列表…").triggered.connect(lambda: self.reminder_list_requested.emit())
        menu.addAction("🍅 番茄钟…").triggered.connect(lambda: self.pomodoro_requested.emit())
        menu.addSeparator()
        self._quiet_action = menu.addAction("安静模式")
        self._quiet_action.setCheckable(True)
        self._quiet_action.triggered.connect(lambda checked: self.quiet_toggled.emit(bool(checked)))
        menu.addSeparator()
        menu.addAction("设置…").triggered.connect(lambda: self.settings_requested.emit())
        menu.addAction("关于 PetGen").triggered.connect(lambda: self.about_requested.emit())
        menu.addSeparator()
        menu.addAction("退出").triggered.connect(lambda: self.quit_requested.emit())
        return menu

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show_pet_requested.emit()
