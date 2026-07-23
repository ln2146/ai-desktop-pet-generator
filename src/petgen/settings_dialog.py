from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from petgen import __version__
from petgen.datadir import data_dir
from petgen.envfile import load_env_file
from petgen.personalities import PERSONALITIES

_AI_FIELDS = {
    "ai_api_key": "ai.api_key",
    "ai_base_url": "ai.base_url",
    "ai_image_model": "ai.image_model",
    "ai_text_model": "ai.text_model",
}
_PET_FIELDS_BOOL = {
    "pet_motion": "pet.motion_enabled",
    "pet_sound": "pet.sound_enabled",
    "pet_click_chat": "ai.click_chat",
}


class SettingsDialog(QDialog):
    applied = Signal()

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("PetGen 设置")
        self.resize(520, 560)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_ai_tab(), "AI 服务")
        tabs.addTab(self._build_pet_tab(), "宠物")
        tabs.addTab(self._build_about_tab(), "关于")
        root.addWidget(tabs)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save = QPushButton("保存")
        save.clicked.connect(self._save)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

        self.load_values()

    # --- tabs ---------------------------------------------------------------

    def _build_ai_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.ai_api_key = QLineEdit()
        self.ai_api_key.setEchoMode(QLineEdit.Password)
        self._ai_eye = QPushButton("👁")
        self._ai_eye.setFixedWidth(34)
        self._ai_eye.setCheckable(True)
        self._ai_eye.toggled.connect(
            lambda on: self.ai_api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key"))
        key_row.addWidget(self.ai_api_key, 1)
        key_row.addWidget(self._ai_eye)
        layout.addLayout(key_row)

        self.ai_base_url = QLineEdit()
        layout.addWidget(QLabel("Base URL"))
        layout.addWidget(self.ai_base_url)
        self.ai_image_model = QLineEdit()
        layout.addWidget(QLabel("图像模型"))
        layout.addWidget(self.ai_image_model)
        self.ai_text_model = QLineEdit()
        layout.addWidget(QLabel("文本模型"))
        layout.addWidget(self.ai_text_model)

        fill = QPushButton("从 .env 填充")
        fill.clicked.connect(self._fill_from_env)
        layout.addWidget(fill)
        layout.addStretch(1)
        return w

    def _build_pet_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("宠物缩放"))
        self.pet_scale = QDoubleSpinBox()
        self.pet_scale.setRange(0.5, 3.0)
        self.pet_scale.setSingleStep(0.25)
        scale_row.addWidget(self.pet_scale)
        scale_row.addStretch(1)
        layout.addLayout(scale_row)

        self.pet_motion = QCheckBox("开启动画（呼吸/动作）")
        self.pet_sound = QCheckBox("音效反馈")
        self.pet_click_chat = QCheckBox("点击宠物时用 AI 回一句话")
        layout.addWidget(self.pet_motion)
        layout.addWidget(self.pet_sound)
        layout.addWidget(self.pet_click_chat)

        layout.addWidget(QLabel("人格"))
        self.pet_personality = QComboBox()
        self._personality_keys: list[str] = []
        for key, p in PERSONALITIES.items():
            self._personality_keys.append(key)
            self.pet_personality.addItem(p.label, key)
        layout.addWidget(self.pet_personality)
        layout.addStretch(1)
        return w

    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel(f"PetGen v{__version__}"))
        layout.addWidget(QLabel(f"数据目录：{data_dir()}"))
        try:
            from petgen.store import AiEventStore

            stats = AiEventStore().stats()
            layout.addWidget(QLabel(f"已记录 AI 事件：{stats['total']} 条（今日 {stats['today_count']}）"))
        except Exception:
            pass
        layout.addStretch(1)
        return w

    # --- value transfer -----------------------------------------------------

    def load_values(self) -> None:
        for widget_name, key in _AI_FIELDS.items():
            value = self._settings.get(key, "")
            getattr(self, widget_name).setText("" if value is None else str(value))
        for widget_name, key in _PET_FIELDS_BOOL.items():
            getattr(self, widget_name).setChecked(bool(self._settings.get(key, widget_name == "pet_motion")))
        self.pet_scale.setValue(float(self._settings.get("pet.scale", 1.0)))
        sel = self._settings.get("pet.personality", "warm")
        idx = self._personality_keys.index(sel) if sel in self._personality_keys else 0
        self.pet_personality.setCurrentIndex(idx)

    def apply_values(self) -> None:
        values = {
            _AI_FIELDS["ai_api_key"]: self.ai_api_key.text(),
            _AI_FIELDS["ai_base_url"]: self.ai_base_url.text(),
            _AI_FIELDS["ai_image_model"]: self.ai_image_model.text(),
            _AI_FIELDS["ai_text_model"]: self.ai_text_model.text(),
            _PET_FIELDS_BOOL["pet_motion"]: self.pet_motion.isChecked(),
            _PET_FIELDS_BOOL["pet_sound"]: self.pet_sound.isChecked(),
            _PET_FIELDS_BOOL["pet_click_chat"]: self.pet_click_chat.isChecked(),
            "pet.scale": float(self.pet_scale.value()),
            "pet.personality": self._personality_keys[self.pet_personality.currentIndex()],
        }
        self._settings.set_many(values)
        return values

    def _save(self) -> None:
        self.apply_values()
        self.applied.emit()
        self.accept()

    def _fill_from_env(self) -> None:
        load_env_file(None)
        mapping = {
            self.ai_api_key: "OPENAI_API_KEY",
            self.ai_base_url: "OPENAI_BASE_URL",
            self.ai_image_model: "OPENAI_IMAGE_MODEL",
            self.ai_text_model: "OPENAI_TEXT_MODEL",
        }
        for widget, env_name in mapping.items():
            if not widget.text():
                value = os.environ.get(env_name, "")
                if value:
                    widget.setText(value)
