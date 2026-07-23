from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_THUMB = 96
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
        self.setWindowTitle("创建新宠物")
        self._images: list[str] = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("描述（这只宠物长什么样、什么性格）"))
        self.description = QTextEdit()
        self.description.setPlaceholderText("例如：一只圆滚滚的水豚程序员，戴小耳机，温柔聪明")
        layout.addWidget(self.description)

        img_row = QHBoxLayout()
        add_img = QPushButton("添加参考图…")
        add_img.clicked.connect(self._add_image)
        self._img_label = QLabel("未选择参考图")
        img_row.addWidget(add_img)
        img_row.addWidget(self._img_label, 1)
        layout.addLayout(img_row)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _add_image(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择参考图", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if paths:
            self._images.extend(paths)
            self._img_label.setText(f"{len(self._images)} 张参考图")

    def result_values(self) -> tuple[str, list[str]]:
        return self.description.toPlainText().strip(), list(self._images)


class _PetCard(QFrame):
    selected = Signal(str)
    previewed = Signal(str)
    revealed = Signal(str)
    deleted = Signal(str)

    def __init__(self, record, selected: bool, parent=None) -> None:
        super().__init__(parent)
        self._id = record.id
        self._dir = record.dir_path
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame{background:#fafafa;border:1px solid #e2e2e2;border-radius:8px;}" if not selected
                           else "QFrame{background:#eef2ff;border:1px solid #9aa6ff;border-radius:8px;}")
        layout = QVBoxLayout(self)
        thumb = QLabel()
        thumb.setFixedSize(_THUMB, _THUMB)
        thumb.setAlignment(Qt.AlignCenter)
        thumb_path = record.preview_path or record.sprite_path
        if thumb_path and Path(thumb_path).is_file():
            pm = QPixmap(thumb_path).scaled(_THUMB, _THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(pm)
        layout.addWidget(thumb, 0, Qt.AlignHCenter)
        name = QLabel(record.display_name or record.id)
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        layout.addWidget(name)

        btns = QHBoxLayout()
        sel = QPushButton("选择")
        sel.clicked.connect(lambda: self.selected.emit(self._id))
        prev = QPushButton("预览")
        prev.clicked.connect(lambda: self.previewed.emit(self._id))
        rev = QPushButton("显示")
        rev.clicked.connect(lambda: self.revealed.emit(self._dir))
        delete = QPushButton("删除")
        delete.clicked.connect(lambda: self.deleted.emit(self._id))
        for b in (sel, prev, rev, delete):
            btns.addWidget(b)
        layout.addLayout(btns)


class LibraryDialog(QDialog):
    pet_selected = Signal(str)
    preview_requested = Signal(str)
    delete_requested = Signal(str)
    import_requested = Signal(str)
    create_requested = Signal(str, list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("宠物库")
        self.resize(560, 480)
        self._grid_layout: QGridLayout | None = None
        self._cards: list[_PetCard] = []

        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self._create_btn = QPushButton("✨ 创建新宠物…")
        self._create_btn.clicked.connect(self._on_create)
        import_btn = QPushButton("导入宠物文件夹…")
        import_btn.clicked.connect(self._on_import)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(lambda: self.refresh_requested.emit())
        toolbar.addWidget(self._create_btn)
        toolbar.addWidget(import_btn)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self._progress = QLabel("")
        self._progress.setStyleSheet("color:#666;")
        root.addWidget(self._progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._grid_layout = QGridLayout(container)
        self._grid_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        root.addWidget(scroll)

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
