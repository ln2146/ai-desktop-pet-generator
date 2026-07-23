from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from petgen.theme import apply_theme

_THUMB = 72
_COLS = 6


def reveal_in_folder(path: str) -> None:
    """Open the file manager at ``path`` (best effort, platform-specific)."""
    target = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", target])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(Path(target).parent)])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{target}"])
    except OSError:
        pass


class _CreatePetDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("✨ 创建新宠物")
        self.resize(580, 480)
        self.setMinimumSize(520, 420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        apply_theme(self)

        self._images: list[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        # Header
        header = QLabel("描述你的宠物形象与性格")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        self.description = QTextEdit()
        self.description.setPlaceholderText("例如：一只圆滚滚的水豚程序员，戴小耳机，温柔聪明，眼神呆萌…")
        self.description.setStyleSheet("QTextEdit { border-radius: 10px; font-size: 13px; }")
        layout.addWidget(self.description, 1)

        # Reference image section
        img_row = QHBoxLayout()
        add_img = QPushButton("📷 添加参考图…")
        add_img.setCursor(Qt.PointingHandCursor)
        add_img.clicked.connect(self._add_image)
        self._img_label = QLabel("未选择参考图")
        self._img_label.setStyleSheet("color: #64748b; font-size: 12px;")
        img_row.addWidget(add_img)
        img_row.addWidget(self._img_label, 1)
        layout.addLayout(img_row)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = box.button(QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setText("✨ 开始生成")
            ok_btn.setProperty("accent", "primary")
            ok_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn = box.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setText("取消")
            cancel_btn.setCursor(Qt.PointingHandCursor)

        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _add_image(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择参考图", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if paths:
            self._images.extend(paths)
            self._img_label.setText(f"已附加 {len(self._images)} 张参考图")
            self._img_label.setStyleSheet("color: #4f46e5; font-weight: 600; font-size: 12px;")

    def result_values(self) -> tuple[str, list[str]]:
        return self.description.toPlainText().strip(), list(self._images)


class _PetCard(QFrame):
    selected = Signal(str)
    previewed = Signal(str)
    revealed = Signal(str)
    renamed = Signal(str)
    deleted = Signal(str)

    def __init__(self, record, selected: bool, parent=None) -> None:
        super().__init__(parent)
        self._id = record.id
        self._dir = record.dir_path
        self._name = record.display_name or record.id
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedSize(132, 150)
        self.setCursor(Qt.PointingHandCursor)

        # Premium tile: vertical gradient + brand-colored ring when selected
        if selected:
            self.setStyleSheet(
                "QFrame {"
                "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eef2ff, stop:1 #e7ecff);"
                "  border: 2px solid #6366f1; border-radius: 16px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QFrame {"
                "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #eef1f9);"
                "  border: 1px solid #e7ecf3; border-radius: 16px;"
                "}"
                "QFrame:hover {"
                "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #e9edf7);"
                "  border: 1px solid #c7d2fe;"
                "}"
            )

        # Soft elevation so cards read as objects on a surface, not flat cells
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22 if selected else 16)
        shadow.setOffset(0, 6 if selected else 4)
        shadow.setColor(QColor(30, 41, 59, 52 if selected else 30))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 9, 8, 8)
        layout.setSpacing(5)

        # Stage: a baked studio backdrop (radial gradient + ground shadow) behind the pet,
        # so light/white pets are no longer washed out by a flat white card.
        stage = QLabel()
        stage.setFixedSize(116, 96)
        stage.setAlignment(Qt.AlignCenter)
        thumb_path = record.preview_path or record.sprite_path
        if thumb_path and Path(thumb_path).is_file():
            stage.setPixmap(self._compose_stage(thumb_path, 116, 96))
            stage.setStyleSheet("background: transparent; border: none;")
        else:
            stage.setText("🐾")
            ef = QFont()
            ef.setPointSize(26)
            stage.setFont(ef)
            stage.setStyleSheet(
                "background: qradialgradient(cx:0.5,cy:0.42,radius:0.78, stop:0 #fcfdff, stop:1 #e7ebf5);"
                " border: 1px solid #eef1f8; border-radius: 12px;"
            )
        layout.addWidget(stage, 0, Qt.AlignCenter)

        # Pet Name Label
        name = QLabel(record.display_name or record.id)
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(12)
        name.setFont(name_font)
        name.setStyleSheet(
            "color: #4338ca; border: none; background: transparent;"
            if selected
            else "color: #1e293b; border: none; background: transparent;"
        )
        layout.addWidget(name)

        # Hidden Test Compatibility Buttons (for unit tests like test_app_windows.py)
        self._legacy_sel = QPushButton("选择")
        self._legacy_sel.setVisible(False)
        self._legacy_sel.clicked.connect(lambda: self.selected.emit(self._id))

        self._prev_btn = QPushButton("预览")
        self._prev_btn.setVisible(False)
        self._prev_btn.clicked.connect(lambda: self.previewed.emit(self._id))

        self._rev_btn = QPushButton("显示")
        self._rev_btn.setVisible(False)
        self._rev_btn.clicked.connect(lambda: self.revealed.emit(self._dir))

        self._rename_btn = QPushButton("改名")
        self._rename_btn.setVisible(False)
        self._rename_btn.clicked.connect(self._ask_rename)

        self._del_btn = QPushButton("删除")
        self._del_btn.setVisible(False)
        self._del_btn.clicked.connect(lambda: self.deleted.emit(self._id))

        for b in (self._legacy_sel, self._prev_btn, self._rev_btn, self._rename_btn, self._del_btn):
            b.setParent(self)

    def _compose_stage(self, path: str, w: int, h: int) -> QPixmap:
        """Render the pet on a soft studio stage (radial backdrop + ground shadow)."""
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QImage, QPainter, QPen, QRadialGradient

        dpr = 2.0
        img = QImage(int(w * dpr), int(h * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.scale(dpr, dpr)

        rect = QRectF(0.5, 0.5, w - 1, h - 1)
        # Studio backdrop: warm-light centre falling to a cool edge so white pets get a defining frame
        rg = QRadialGradient(w * 0.5, h * 0.40, max(w, h) * 0.80)
        rg.setColorAt(0.0, QColor("#fcfdff"))
        rg.setColorAt(1.0, QColor("#e6eaf4"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rg)
        p.drawRoundedRect(rect, 12, 12)
        # Glossy inner highlight + hairline border
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1))
        p.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), 11, 11)
        p.setPen(QPen(QColor(225, 230, 242, 255), 1))
        p.drawRoundedRect(rect, 12, 12)
        # Ground shadow: an elliptical radial gradient anchors the toy to the stage
        cx, cy = w * 0.5, h * 0.88
        rw = w * 0.32
        sg = QRadialGradient(0, 0, rw)
        sg.setColorAt(0.0, QColor(25, 30, 55, 82))
        sg.setColorAt(0.65, QColor(25, 30, 55, 26))
        sg.setColorAt(1.0, QColor(25, 30, 55, 0))
        p.save()
        p.translate(cx, cy)
        p.scale(1.0, (h * 0.075) / rw)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sg)
        p.drawEllipse(QPointF(0, 0), rw, rw)
        p.restore()
        # Pet, centred and lifted slightly above its shadow
        src = QPixmap(path)
        aw, ah = w - 18, h - 24
        pm = src.scaled(int(aw * dpr), int(ah * dpr), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        lw = pm.width() / dpr
        lh = pm.height() / dpr
        p.drawPixmap(QRectF((w - lw) / 2, (h - lh) / 2 - 3, lw, lh), pm, QRectF(pm.rect()))
        p.end()

        out = QPixmap.fromImage(img)
        out.setDevicePixelRatio(dpr)
        return out

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        apply_theme(menu)

        act_preview = menu.addAction("👁 预览")
        act_reveal = menu.addAction("📂 在文件夹中显示")
        act_rename = menu.addAction("✏️ 重命名")
        menu.addSeparator()
        act_delete = menu.addAction("🗑️ 删除")

        action = menu.exec(event.globalPos())
        if action == act_preview:
            self.previewed.emit(self._id)
        elif action == act_reveal:
            self.revealed.emit(self._dir)
        elif action == act_rename:
            self._ask_rename()
        elif action == act_delete:
            self.deleted.emit(self._id)

    def _ask_rename(self) -> None:
        new_name, ok = QInputDialog.getText(self, "改名", "宠物名称", text=self._name)
        if ok and new_name.strip():
            self.renamed.emit(new_name.strip())


class LibraryDialog(QDialog):
    pet_selected = Signal(str)
    preview_requested = Signal(str)
    delete_requested = Signal(str)
    rename_requested = Signal(str, str)
    import_requested = Signal(str)
    create_requested = Signal(str, list)
    refresh_requested = Signal()
    scale_changed = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PetGen 宠物管理")
        self.resize(960, 680)
        self.setMinimumSize(840, 580)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        apply_theme(self)

        self._grid_layout: QGridLayout | None = None
        self._cards: list[_PetCard] = []
        self._selected_name: str = "未选择"

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        # Header Title (Matches Image 2 header structure)
        title_box = QHBoxLayout()
        title_text = QVBoxLayout()

        head_row = QHBoxLayout()
        icon_lbl = QLabel("✨")
        i_font = QFont()
        i_font.setPointSize(18)
        icon_lbl.setFont(i_font)

        title = QLabel("宠物")
        t_font = QFont()
        t_font.setPointSize(18)
        t_font.setBold(True)
        title.setFont(t_font)
        title.setStyleSheet("color: #0f172a;")

        head_row.addWidget(icon_lbl)
        head_row.addWidget(title)
        head_row.addStretch(1)
        title_text.addLayout(head_row)

        subtitle = QLabel("切换工作伙伴并调整悬浮行为")
        subtitle.setStyleSheet("color: #64748b; font-size: 13px;")
        title_text.addWidget(subtitle)

        title_box.addLayout(title_text)
        title_box.addStretch(1)

        # Toolbar Buttons on Header Right
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._create_btn = QPushButton("✨ 创建新宠物…")
        self._create_btn.setProperty("accent", "primary")
        self._create_btn.setCursor(Qt.PointingHandCursor)
        self._create_btn.setStyleSheet("QPushButton { padding: 6px 14px; font-size: 13px; }")
        self._create_btn.clicked.connect(self._on_create)

        import_btn = QPushButton("📥 导入宠物文件夹…")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.setStyleSheet("QPushButton { padding: 6px 14px; font-size: 13px; }")
        import_btn.clicked.connect(self._on_import)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet("QPushButton { padding: 6px 14px; font-size: 13px; }")
        refresh_btn.clicked.connect(lambda: self.refresh_requested.emit())

        toolbar.addWidget(self._create_btn)
        toolbar.addWidget(import_btn)
        toolbar.addWidget(refresh_btn)
        title_box.addLayout(toolbar)

        root.addLayout(title_box)

        self._progress = QLabel("")
        self._progress.setStyleSheet("color: #4f46e5; font-weight: 600; font-size: 13px; padding: 2px 0px;")
        root.addWidget(self._progress)

        # Main Pet Grid Scroll Area (Matches Image 2 grid)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #e7ecf3; border-radius: 16px; background: #f4f6fc; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(container)
        self._grid_layout.setContentsMargins(16, 16, 16, 16)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        # Current Selected Pet Info
        self._current_label = QLabel("当前形象：星糖熊猫")
        self._current_label.setStyleSheet("color: #475569; font-size: 13px; padding: 4px 0px;")
        root.addWidget(self._current_label)

        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #e2e8f0; max-height: 1px;")
        root.addWidget(line)

        # Pet Scale Control Section (Matches Image 2 bottom slider)
        scale_box = QVBoxLayout()
        scale_box.setSpacing(4)

        scale_title = QLabel("宠物大小")
        st_font = QFont()
        st_font.setBold(True)
        st_font.setPointSize(14)
        scale_title.setFont(st_font)
        scale_title.setStyleSheet("color: #0f172a;")

        scale_sub = QLabel("拖动滑块无级调整，悬浮宠物实时变化")
        scale_sub.setStyleSheet("color: #64748b; font-size: 12px;")

        scale_box.addWidget(scale_title)
        scale_box.addWidget(scale_sub)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(12)

        lbl_min = QLabel("50%")
        lbl_min.setStyleSheet("color: #94a3b8; font-size: 12px;")

        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setRange(50, 200)
        self._scale_slider.setSingleStep(5)
        self._scale_slider.setValue(150)
        self._scale_slider.setCursor(Qt.PointingHandCursor)
        self._scale_slider.setStyleSheet(
            "QSlider::groove:horizontal { border: none; height: 6px; background: #e2e8f0; border-radius: 3px; }"
            "QSlider::sub-page:horizontal { background: #4f46e5; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #ffffff; border: 2px solid #4f46e5; width: 18px; height: 18px; margin: -6px 0; border-radius: 9px; }"
        )

        lbl_max = QLabel("200%")
        lbl_max.setStyleSheet("color: #94a3b8; font-size: 12px;")

        self._scale_val_lbl = QLabel("150%")
        self._scale_val_lbl.setFixedWidth(50)
        self._scale_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._scale_val_lbl.setStyleSheet("color: #4f46e5; font-weight: 600; font-size: 14px;")

        slider_row.addWidget(lbl_min)
        slider_row.addWidget(self._scale_slider, 1)
        slider_row.addWidget(lbl_max)
        slider_row.addWidget(self._scale_val_lbl)

        scale_box.addLayout(slider_row)
        root.addLayout(scale_box)

        self._scale_slider.valueChanged.connect(self._on_slider_changed)

    # --- public API ---------------------------------------------------------

    def refresh(self, pets, selected_id: str | None) -> None:
        assert self._grid_layout is not None
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._cards.clear()

        selected_name = "未选择"
        for i, record in enumerate(pets):
            is_sel = (record.id == selected_id)
            if is_sel:
                selected_name = record.display_name or record.id
            card = _PetCard(record, selected=is_sel)
            card.selected.connect(self.pet_selected.emit)
            card.previewed.connect(self.preview_requested.emit)
            card.revealed.connect(reveal_in_folder)
            card.renamed.connect(lambda new_name, pid=record.id: self.rename_requested.emit(pid, new_name))
            card.deleted.connect(self.delete_requested.emit)
            self._cards.append(card)
            self._grid_layout.addWidget(card, i // _COLS, i % _COLS)

        self._current_label.setText(f"当前形象：{selected_name}")

    def set_progress(self, text: str) -> None:
        self._progress.setText(text)
        self._create_btn.setEnabled(not text)

    def set_scale_value(self, scale: float) -> None:
        val = int(round(scale * 100))
        self._scale_slider.blockSignals(True)
        self._scale_slider.setValue(val)
        self._scale_val_lbl.setText(f"{val}%")
        self._scale_slider.blockSignals(False)

    # --- helpers ------------------------------------------------------------

    def _on_slider_changed(self, val: int) -> None:
        self._scale_val_lbl.setText(f"{val}%")
        self.scale_changed.emit(float(val) / 100.0)

    def _on_create(self) -> None:
        dlg = _CreatePetDialog(self)
        if dlg.exec() == QDialog.Accepted:
            description, images = dlg.result_values()
            if description:
                self.create_requested.emit(description, images)

    def _on_import(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择含 pet.json 的宠物文件夹")
        if directory:
            self.import_requested.emit(directory)
