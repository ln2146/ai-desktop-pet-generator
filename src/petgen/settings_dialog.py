from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
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
from petgen.voicepack import load_catalog
from petgen.theme import apply_theme

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


def _create_card_container(title: str, subtitle: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setStyleSheet(
        "QFrame {"
        "  background-color: #ffffff;"
        "  border: 1px solid #e2e8f0;"
        "  border-radius: 12px;"
        "}"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(10)

    header = QLabel(title)
    h_font = QFont()
    h_font.setBold(True)
    h_font.setPointSize(12)
    header.setFont(h_font)
    header.setStyleSheet("color: #0f172a; border: none;")
    layout.addWidget(header)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setStyleSheet("color: #64748b; font-size: 11px; border: none;")
        layout.addWidget(sub)

    return card, layout


class SettingsDialog(QDialog):
    applied = Signal()

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("PetGen 设置中心")
        self.resize(680, 680)
        self.setMinimumSize(620, 620)
        apply_theme(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # Header Title
        head = QLabel("⚙️ 全局设置与偏好配置")
        h_font = QFont()
        h_font.setPointSize(14)
        h_font.setBold(True)
        head.setFont(h_font)
        head.setStyleSheet("color: #0f172a;")
        root.addWidget(head)

        tabs = QTabWidget()
        tabs.addTab(self._build_ai_tab(), "🤖 AI 服务")
        tabs.addTab(self._build_pet_tab(), "🐶 宠物行为")
        tabs.addTab(self._build_about_tab(), "ℹ️ 关于 PetGen")
        root.addWidget(tabs, 1)

        # Action Buttons Bottom Bar
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)

        fill_btn = QPushButton("📄 从 .env 填充")
        fill_btn.setCursor(Qt.PointingHandCursor)
        fill_btn.clicked.connect(self._fill_from_env)

        cancel = QPushButton("取消")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)

        save = QPushButton("保存设置")
        save.setProperty("accent", "primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)

        buttons.addWidget(fill_btn)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self.load_values()

    # --- tabs ---------------------------------------------------------------

    def _build_ai_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # API Credentials Card
        card1, c1_layout = _create_card_container("API 凭据配置", "用于调用 OpenAI 或兼容协议的大模型服务")

        c1_layout.addWidget(QLabel("API Key"))
        self.ai_api_key = QLineEdit()
        self.ai_api_key.setPlaceholderText("sk-...")
        self.ai_api_key.setEchoMode(QLineEdit.Password)
        self._ai_eye = QPushButton("👁")
        self._ai_eye.setFixedWidth(36)
        self._ai_eye.setCheckable(True)
        self._ai_eye.setCursor(Qt.PointingHandCursor)
        self._ai_eye.toggled.connect(
            lambda on: self.ai_api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        key_row = QHBoxLayout()
        key_row.addWidget(self.ai_api_key, 1)
        key_row.addWidget(self._ai_eye)
        c1_layout.addLayout(key_row)

        c1_layout.addWidget(QLabel("Base URL (自定义中转接口，留空使用官方)"))
        self.ai_base_url = QLineEdit()
        self.ai_base_url.setPlaceholderText("https://api.openai.com/v1")
        c1_layout.addWidget(self.ai_base_url)
        layout.addWidget(card1)

        # Model Selection Card
        card2, c2_layout = _create_card_container("模型选择", "图像生成与文本对话模型")

        grid = QHBoxLayout()
        v1 = QVBoxLayout()
        v1.addWidget(QLabel("图像模型"))
        self.ai_image_model = QLineEdit()
        self.ai_image_model.setPlaceholderText("dall-e-3")
        v1.addWidget(self.ai_image_model)
        grid.addLayout(v1)

        v2 = QVBoxLayout()
        v2.addWidget(QLabel("文本模型"))
        self.ai_text_model = QLineEdit()
        self.ai_text_model.setPlaceholderText("gpt-4o-mini")
        v2.addWidget(self.ai_text_model)
        grid.addLayout(v2)

        c2_layout.addLayout(grid)
        layout.addWidget(card2)

        layout.addStretch(1)
        return w

    def _build_pet_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Visual & Animation Card
        card1, c1_layout = _create_card_container("外观与动作", "调整桌宠在屏幕上的尺寸与动画显示")
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("宠物显示缩放倍率："))
        self.pet_scale = QDoubleSpinBox()
        self.pet_scale.setRange(0.5, 3.0)
        self.pet_scale.setSingleStep(0.25)
        self.pet_scale.setFixedWidth(80)
        scale_row.addWidget(self.pet_scale)
        scale_row.addStretch(1)
        c1_layout.addLayout(scale_row)

        self.pet_motion = QCheckBox("开启动画动作与呼吸效果")
        self.pet_sound = QCheckBox("开启音效反馈")
        self.pet_click_chat = QCheckBox("点击宠物时触发 AI 实时智能对话")
        c1_layout.addWidget(self.pet_motion)
        c1_layout.addWidget(self.pet_sound)
        c1_layout.addWidget(self.pet_click_chat)
        layout.addWidget(card1)

        # Personality Card
        card2, c2_layout = _create_card_container("宠物性格模式", "影响互动时的回复语气与动作表现")
        self.pet_personality = QComboBox()
        self._personality_keys: list[str] = []
        for key, p in PERSONALITIES.items():
            self._personality_keys.append(key)
            self.pet_personality.addItem(f"✨ {p.label}", key)
        c2_layout.addWidget(self.pet_personality)
        layout.addWidget(card2)

        # Voice Pack Card
        card3, c3_layout = _create_card_container("语音包", "切换桌宠的说话音色与反馈音效（语音由本地 TTS 合成、音效为程序合成，均无版权问题）")
        self.voice_pack = QComboBox()
        self._voice_pack_keys: list[str] = []
        for key, pack in load_catalog().items():
            self._voice_pack_keys.append(key)
            self.voice_pack.addItem(f"{pack.emoji} {pack.display_name}", key)
        voice_row = QHBoxLayout()
        voice_row.addWidget(self.voice_pack, 1)
        preview_voice = QPushButton("▶ 试听")
        preview_voice.setCursor(Qt.PointingHandCursor)
        preview_voice.clicked.connect(self._preview_voice)
        voice_row.addWidget(preview_voice)
        c3_layout.addLayout(voice_row)
        layout.addWidget(card3)

        layout.addStretch(1)
        return w

    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        card, c_layout = _create_card_container(f"PetGen 桌宠小助手 v{__version__}", "AI 智能桌面灵动宠物构建平台")

        c_layout.addWidget(QLabel(f"📂 数据目录：{data_dir()}"))
        try:
            from petgen.store import AiEventStore

            stats = AiEventStore().stats()
            c_layout.addWidget(QLabel(f"📊 已记录 AI 互动事件：{stats['total']} 条（今日 {stats['today_count']} 条）"))
        except Exception:
            pass

        layout.addWidget(card)
        layout.addStretch(1)
        return w

    # --- value transfer -----------------------------------------------------

    def load_values(self) -> None:
        for widget_name, key in _AI_FIELDS.items():
            value = self._settings.get(key, "")
            getattr(self, widget_name).setText("" if value is None else str(value))
        for widget_name, key in _PET_FIELDS_BOOL.items():
            getattr(self, widget_name).setChecked(bool(self._settings.get(key, widget_name == "pet_motion")))
        self.pet_scale.setValue(float(self._settings.get("pet.scale", 1.5)))
        sel = self._settings.get("pet.personality", "warm")
        idx = self._personality_keys.index(sel) if sel in self._personality_keys else 0
        self.pet_personality.setCurrentIndex(idx)
        vpack = self._settings.get("pet.voice_pack", "soft-meow")
        vidx = self._voice_pack_keys.index(vpack) if vpack in self._voice_pack_keys else 0
        self.voice_pack.setCurrentIndex(vidx)

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
            "pet.voice_pack": self._voice_pack_keys[self.voice_pack.currentIndex()],
        }
        self._settings.set_many(values)
        return values

    def _save(self) -> None:
        self.apply_values()
        self.applied.emit()
        self.accept()

    def _preview_voice(self) -> None:
        # Preview the currently selected pack live (no save required).
        try:
            from petgen.speak import VoicePackService
            from petgen.voicepack import load_catalog

            pack_id = self._voice_pack_keys[self.voice_pack.currentIndex()]
            pack = load_catalog().get(pack_id)
            if pack is None:
                return
            VoicePackService(pack, enabled=True).preview()
        except Exception:
            pass

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
