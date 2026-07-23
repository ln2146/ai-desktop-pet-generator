from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from petgen.theme import apply_theme

_THUMB = 100
_COLS = 3


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
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(250)

        if selected:
            self.setStyleSheet(
                "QFrame {"
                "  background: #f5f7ff;"
                "  border: 2px solid #6366f1;"
                "  border-radius: 12px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QFrame {"
                "  background: #ffffff;"
                "  border: 1px solid #e2e8f0;"
                "  border-radius: 12px;"
                "}"
                "QFrame:hover {"
                "  border-color: #a5b4fc;"
                "}"
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Thumbnail with container box
        thumb_box = QWidget()
        thumb_box.setFixedSize(_THUMB + 16, _THUMB + 16)
        thumb_box.setStyleSheet("background: #f8fafc; border-radius: 12px; border: 1px solid #f1f5f9;")
        thumb_box_layout = QVBoxLayout(thumb_box)
        thumb_box_layout.setContentsMargins(0, 0, 0, 0)

        thumb = QLabel()
        thumb.setFixedSize(_THUMB, _THUMB)
        thumb.setAlignment(Qt.AlignCenter)
        thumb_path = record.preview_path or record.sprite_path
        if thumb_path and Path(thumb_path).is_file():
            pm = QPixmap(thumb_path).scaled(_THUMB, _THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(pm)
        else:
            thumb.setText("🐾")
            font = QFont()
            font.setPointSize(28)
            thumb.setFont(font)
        thumb_box_layout.addWidget(thumb, 0, Qt.AlignCenter)
        layout.addWidget(thumb_box, 0, Qt.AlignHCenter)

        # Name label
        name = QLabel(record.display_name or record.id)
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(13)
        name.setFont(name_font)
        name.setStyleSheet("color: #0f172a; border: none; background: transparent;")
        layout.addWidget(name)

        if selected:
            badge = QLabel("✓ 当前已在桌面使用")
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet("color: #4f46e5; font-weight: 600; font-size: 11px; border: none; background: transparent;")
            layout.addWidget(badge)

        # Action Buttons Layout: 2 rows for clear typography & spacious layout
        # Row 1: Primary "选择" Action Button
        sel = QPushButton("选择" if not selected else "重新选择")
        if not selected:
            sel.setProperty("accent", "primary")
        sel.setCursor(Qt.PointingHandCursor)
        sel.setStyleSheet("QPushButton { padding: 6px 12px; font-weight: 600; }")
        sel.clicked.connect(lambda: self.selected.emit(self._id))
        layout.addWidget(sel)

        # Row 2: Secondary buttons (预览, 显示, 改名, 删除)
        sub_btns = QHBoxLayout()
        sub_btns.setSpacing(4)

        btn_style = "QPushButton { padding: 4px 6px; font-size: 11px; }"

        prev = QPushButton("预览")
        prev.setCursor(Qt.PointingHandCursor)
        prev.setStyleSheet(btn_style)
        prev.clicked.connect(lambda: self.previewed.emit(self._id))

        rev = QPushButton("显示")
        rev.setCursor(Qt.PointingHandCursor)
        rev.setStyleSheet(btn_style)
        rev.clicked.connect(lambda: self.revealed.emit(self._dir))

        rename = QPushButton("改名")
        rename.setCursor(Qt.PointingHandCursor)
        rename.setStyleSheet(btn_style)
        rename.clicked.connect(self._ask_rename)

        delete = QPushButton("删除")
        delete.setProperty("accent", "danger")
        delete.setCursor(Qt.PointingHandCursor)
        delete.setStyleSheet(btn_style)
        delete.clicked.connect(lambda: self.deleted.emit(self._id))

        for b in (prev, rev, rename, delete):
            sub_btns.addWidget(b, 1)

        layout.addLayout(sub_btns)

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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PetGen 宠物库")
        self.resize(960, 680)
        self.setMinimumSize(840, 580)
        apply_theme(self)

        self._grid_layout: QGridLayout | None = None
        self._cards: list[_PetCard] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Header Title
        title_box = QHBoxLayout()
        title_text = QVBoxLayout()
        title = QLabel("🐾 宠物画廊与仓库")
        t_font = QFont()
        t_font.setPointSize(16)
        t_font.setBold(True)
        title.setFont(t_font)
        title.setStyleSheet("color: #0f172a;")

        subtitle = QLabel("管理已生成的桌面宠物，随时切换桌面新形象")
        subtitle.setStyleSheet("color: #64748b; font-size: 13px;")
        title_text.addWidget(title)
        title_text.addWidget(subtitle)
        title_box.addLayout(title_text)
        title_box.addStretch(1)
        root.addLayout(title_box)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self._create_btn = QPushButton("✨ 创建新宠物…")
        self._create_btn.setProperty("accent", "primary")
        self._create_btn.setCursor(Qt.PointingHandCursor)
        self._create_btn.setStyleSheet("QPushButton { padding: 8px 18px; font-size: 13px; }")
        self._create_btn.clicked.connect(self._on_create)

        import_btn = QPushButton("📥 导入宠物文件夹…")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-size: 13px; }")
        import_btn.clicked.connect(self._on_import)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-size: 13px; }")
        refresh_btn.clicked.connect(lambda: self.refresh_requested.emit())

        toolbar.addWidget(self._create_btn)
        toolbar.addWidget(import_btn)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self._progress = QLabel("")
        self._progress.setStyleSheet("color: #4f46e5; font-weight: 600; font-size: 13px; padding: 2px 0px;")
        root.addWidget(self._progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #e2e8f0; border-radius: 12px; background: #fafafa; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(container)
        self._grid_layout.setContentsMargins(14, 14, 14, 14)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        self.refresh_requested = Signal()

    # --- public API ---------------------------------------------------------

    def refresh(self, pets, selected_id: str | None) -> None:
        assert self._grid_layout is not None
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._cards.clear()
        for i, record in enumerate(pets):
            card = _PetCard(record, selected=(record.id == selected_id))
            card.selected.connect(self.pet_selected.emit)
            card.previewed.connect(self.preview_requested.emit)
            card.revealed.connect(reveal_in_folder)
            card.renamed.connect(lambda new_name, pid=record.id: self.rename_requested.emit(pid, new_name))
            card.deleted.connect(self.delete_requested.emit)
            self._cards.append(card)
            self._grid_layout.addWidget(card, i // _COLS, i % _COLS)

    def set_progress(self, text: str) -> None:
        self._progress.setText(text)
        self._create_btn.setEnabled(not text)

    # --- helpers ------------------------------------------------------------

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
