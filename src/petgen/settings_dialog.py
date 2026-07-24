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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from petgen import __version__, integrations
from petgen.datadir import data_dir
from petgen.envfile import load_env_file
from petgen.personalities import PERSONALITIES
from petgen.theme import apply_theme
from petgen.voicepack import load_catalog

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
    card.setObjectName("cardContainer")
    card.setStyleSheet(
        "QFrame#cardContainer {"
        "  background-color: #ffffff;"
        "  border: 1px solid #e2e8f0;"
        "  border-radius: 14px;"
        "}"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(12)

    header = QLabel(title)
    h_font = QFont()
    h_font.setBold(True)
    h_font.setPointSize(14)
    header.setFont(h_font)
    header.setStyleSheet("color: #0f172a; border: none; background: transparent;")
    layout.addWidget(header)

    if subtitle:
        sub = QLabel(subtitle)
        sub.setWordWrap(True)  # long subtitles must wrap, else they widen the card and push right-aligned controls off-screen
        sub.setStyleSheet("color: #64748b; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(sub)

    return card, layout


def _create_field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #334155; font-weight: 600; font-size: 12px; border: none; background: transparent;")
    return lbl


def _wrap_tab_scroll(content_widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
    scroll.setWidget(content_widget)
    return scroll


class SettingsDialog(QDialog):
    applied = Signal()

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("PetGen 设置中心")
        self.resize(680, 680)
        self.setMinimumSize(620, 620)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        apply_theme(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(16)

        # Header Title Area
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        head = QLabel("⚙️ 全局设置与偏好配置")
        h_font = QFont()
        h_font.setPointSize(16)
        h_font.setBold(True)
        head.setFont(h_font)
        head.setStyleSheet("color: #0f172a; border: none;")

        subhead = QLabel("配置大模型 API 秘钥、自定义接口地址与桌面宠物交互动作")
        subhead.setStyleSheet("color: #64748b; font-size: 13px; border: none;")

        title_box.addWidget(head)
        title_box.addWidget(subhead)
        root.addLayout(title_box)

        # Tabs (Styled Segmented Control) with ScrollArea wrappers
        tabs = QTabWidget()
        tabs.addTab(_wrap_tab_scroll(self._build_ai_tab()), "🤖  AI 服务")
        tabs.addTab(_wrap_tab_scroll(self._build_pet_tab()), "🐶  宠物行为")
        tabs.addTab(_wrap_tab_scroll(self._build_tools_tab()), "🔌  工具接入")
        tabs.addTab(_wrap_tab_scroll(self._build_about_tab()), "ℹ️  关于 PetGen")
        root.addWidget(tabs, 1)

        # Action Buttons Bottom Bar
        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        fill_btn = QPushButton("从 .env 填充")
        fill_btn.setCursor(Qt.PointingHandCursor)
        fill_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-size: 13px; }")
        fill_btn.clicked.connect(self._fill_from_env)

        cancel = QPushButton("取消")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet("QPushButton { padding: 8px 16px; font-size: 13px; }")
        cancel.clicked.connect(self.reject)

        save = QPushButton("保存设置")
        save.setProperty("accent", "primary")
        save.setCursor(Qt.PointingHandCursor)
        save.setStyleSheet("QPushButton { padding: 8px 20px; font-size: 13px; }")
        save.clicked.connect(self._save)

        buttons.addWidget(fill_btn)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self.load_values()

    # --- tabs ---------------------------------------------------------------

    def _build_ai_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 14, 12, 14)
        layout.setSpacing(14)

        # API Credentials Card
        card1, c1_layout = _create_card_container("API 凭据配置", "用于调用 OpenAI 或兼容 OpenAI 协议的大模型服务")

        c1_layout.addWidget(_create_field_label("API Key"))
        key_box = QHBoxLayout()
        key_box.setSpacing(8)

        self.ai_api_key = QLineEdit()
        self.ai_api_key.setPlaceholderText("sk-...")
        self.ai_api_key.setEchoMode(QLineEdit.Password)

        self._ai_eye = QPushButton("👁")
        self._ai_eye.setFixedWidth(38)
        self._ai_eye.setFixedHeight(36)
        self._ai_eye.setCheckable(True)
        self._ai_eye.setCursor(Qt.PointingHandCursor)
        self._ai_eye.setStyleSheet(
            "QPushButton { border: 1px solid #cbd5e1; background: #ffffff; border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { border-color: #6366f1; background: #f8fafc; }"
            "QPushButton:checked { background: #eef2ff; border-color: #6366f1; }"
        )
        self._ai_eye.toggled.connect(
            lambda on: self.ai_api_key.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )

        key_box.addWidget(self.ai_api_key, 1)
        key_box.addWidget(self._ai_eye)
        c1_layout.addLayout(key_box)

        c1_layout.addWidget(_create_field_label("Base URL (自定义中转接口，留空使用官方)"))
        self.ai_base_url = QLineEdit()
        self.ai_base_url.setPlaceholderText("https://api.openai.com/v1")
        c1_layout.addWidget(self.ai_base_url)
        layout.addWidget(card1)

        # Model Selection Card
        card2, c2_layout = _create_card_container("模型选择", "图像生成与文本对话模型名称")

        grid = QHBoxLayout()
        grid.setSpacing(12)

        v1 = QVBoxLayout()
        v1.setSpacing(6)
        v1.addWidget(_create_field_label("图像模型"))
        self.ai_image_model = QLineEdit()
        self.ai_image_model.setPlaceholderText("dall-e-3")
        v1.addWidget(self.ai_image_model)
        grid.addLayout(v1)

        v2 = QVBoxLayout()
        v2.setSpacing(6)
        v2.addWidget(_create_field_label("文本模型"))
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
        layout.setContentsMargins(0, 14, 12, 14)
        layout.setSpacing(14)

        # Visual & Animation Card
        card1, c1_layout = _create_card_container("外观与动作", "调整桌宠动画显示与悬浮互动行为")
        self.pet_scale = QDoubleSpinBox()
        self.pet_scale.setRange(0.5, 3.0)
        self.pet_scale.setSingleStep(0.25)
        self.pet_scale.setVisible(False)

        self.pet_motion = QCheckBox("开启动画动作与呼吸效果")
        self.pet_sound = QCheckBox("开启音效反馈")
        self.pet_click_chat = QCheckBox("点击宠物时触发 AI 实时智能对话")
        for cb in (self.pet_motion, self.pet_sound, self.pet_click_chat):
            cb.setCursor(Qt.PointingHandCursor)
            cb.setStyleSheet("font-size: 13px; font-weight: 500;")
            c1_layout.addWidget(cb)
        layout.addWidget(card1)

        # Personality Card
        card2, c2_layout = _create_card_container("宠物性格模式", "影响互动时的回复语气与动作表现")
        c2_layout.addWidget(_create_field_label("当前性格特征："))
        self.pet_personality = QComboBox()
        self.pet_personality.setFixedHeight(36)
        self._personality_keys: list[str] = []
        for key, p in PERSONALITIES.items():
            self._personality_keys.append(key)
            self.pet_personality.addItem(f"✨ {p.label}", key)
        c2_layout.addWidget(self.pet_personality)
        layout.addWidget(card2)

        # Voice Pack Card
        card3, c3_layout = _create_card_container("语音包配置", "切换桌宠的说话音色与反馈音效")
        c3_layout.addWidget(_create_field_label("当前语音音色："))
        self.voice_pack = QComboBox()
        self.voice_pack.setFixedHeight(36)
        self._voice_pack_keys: list[str] = []
        for key, pack in load_catalog().items():
            self._voice_pack_keys.append(key)
            self.voice_pack.addItem(f"{pack.emoji} {pack.display_name}", key)

        voice_row = QHBoxLayout()
        voice_row.setSpacing(8)
        voice_row.addWidget(self.voice_pack, 1)
        preview_voice = QPushButton("▶ 试听音色")
        preview_voice.setFixedHeight(36)
        preview_voice.setCursor(Qt.PointingHandCursor)
        preview_voice.clicked.connect(self._preview_voice)
        voice_row.addWidget(preview_voice)
        c3_layout.addLayout(voice_row)
        layout.addWidget(card3)

        layout.addStretch(1)
        return w

    def _build_tools_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 14, 12, 14)
        layout.setSpacing(14)

        card, c_layout = _create_card_container(
            "🔌 AI 工具接入",
            "接通后，桌宠会实时回应 Claude Code / Codex / Antigravity 的任务状态。"
            "点击按钮即时生效（无需「保存设置」），配置文件改动前自动备份。",
        )

        self._tool_rows: dict[str, tuple[QLabel, QCheckBox]] = {}
        for tool in integrations.TOOLS:
            row = QHBoxLayout()
            row.setSpacing(10)
            name = QLabel(integrations.TOOL_LABELS[tool])
            name.setStyleSheet(
                "color: #0f172a; font-weight: 600; font-size: 13px; border: none; background: transparent;"
            )
            chip = QLabel()
            chip.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600; border: none; background: transparent;")
            # A real, globally-themed checkbox replaces the per-widget-styled button
            # (that stylesheet was hiding the button). checked == connected; clicking
            # toggles wiring and refresh_tool_rows reapplies the authoritative state.
            toggle = QCheckBox()
            toggle.setCursor(Qt.PointingHandCursor)
            toggle.clicked.connect(lambda _checked=False, t=tool: self._toggle_tool(t))
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(chip)
            row.addWidget(toggle)
            c_layout.addLayout(row)
            self._tool_rows[tool] = (chip, toggle)

        connect_all = QPushButton("⚡ 一键全部接通")
        connect_all.setProperty("accent", "primary")
        connect_all.setCursor(Qt.PointingHandCursor)
        connect_all.setFixedHeight(36)
        connect_all.clicked.connect(self._connect_all_tools)
        c_layout.addSpacing(4)
        c_layout.addWidget(connect_all)

        layout.addWidget(card)
        layout.addStretch(1)
        self.refresh_tool_rows()
        return w

    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 14, 12, 14)
        layout.setSpacing(14)

        card, c_layout = _create_card_container(f"PetGen 桌宠小助手 v{__version__}", "AI 智能桌面灵动宠物构建平台")

        c_layout.addWidget(_create_field_label(f"📂 数据目录：{data_dir()}"))
        try:
            from petgen.store import AiEventStore

            stats = AiEventStore().stats()
            c_layout.addWidget(_create_field_label(f"📊 已记录 AI 互动事件：{stats['total']} 条（今日 {stats['today_count']} 条）"))
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
        # Refresh the tool-wiring states (the dialog instance is reused across shows);
        # a failure here must never break the dialog itself.
        try:
            if hasattr(self, "_tool_rows"):
                self.refresh_tool_rows()
        except Exception:
            pass

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
        try:
            from petgen.speak import VoicePackService

            pack_id = self._voice_pack_keys[self.voice_pack.currentIndex()]
            pack = load_catalog().get(pack_id)
            if pack is None:
                return
            svc = getattr(self, "_preview_voice_svc", None)
            if svc is None:
                # Keep the service alive on the dialog (the coordinator reuses the
                # dialog for its whole lifetime). TTS / SFX / edge playback are async,
                # so a throwaway service gets GC'd before the sound actually plays.
                svc = VoicePackService(pack, enabled=True)
                self._preview_voice_svc = svc
            else:
                svc.set_pack(pack.id)
            svc.set_enabled(True)  # preview ignores mute / do-not-disturb
            svc.preview()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("voice preview failed")

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

    # --- tool wiring tab ------------------------------------------------------

    _TOOL_CHIP_STYLE = {
        integrations.ToolStatus.CONNECTED: ("✅ 已接通", "#16a34a"),
        integrations.ToolStatus.STALE: ("⚠️ 需重连", "#d97706"),
        integrations.ToolStatus.NOT_CONNECTED: ("○ 未接通", "#64748b"),
        integrations.ToolStatus.NOT_DETECTED: ("未检测到", "#94a3b8"),
    }

    def refresh_tool_rows(self) -> None:
        for tool, (chip, toggle) in self._tool_rows.items():
            try:
                state = integrations.status(tool)
            except Exception:
                # Never let a status probe failure break the dialog.
                chip.setText("状态未知")
                chip.setStyleSheet(
                    "color: #94a3b8; font-size: 12px; font-weight: 600; border: none; background: transparent;"
                )
                toggle.blockSignals(True)
                toggle.setChecked(False)
                toggle.setEnabled(False)
                toggle.blockSignals(False)
                continue
            text, color = self._TOOL_CHIP_STYLE[state.status]
            chip.setText(text)
            chip.setStyleSheet(
                f"color: {color}; font-size: 12px; font-weight: 600; border: none; background: transparent;"
            )
            toggle.setToolTip(state.detail)
            # blockSignals so re-applying the authoritative state neither re-triggers
            # _toggle_tool nor echoes a click's optimistic flip.
            toggle.blockSignals(True)
            if state.status == integrations.ToolStatus.NOT_DETECTED:
                toggle.setEnabled(False)
                toggle.setChecked(False)
            else:
                toggle.setEnabled(True)
                toggle.setChecked(state.status == integrations.ToolStatus.CONNECTED)
            toggle.blockSignals(False)

    def _toggle_tool(self, tool: str) -> None:
        _chip, toggle = self._tool_rows[tool]
        toggle.blockSignals(True)
        try:
            state = integrations.status(tool)
            # revert Qt's optimistic visual flip until the real outcome is known
            toggle.setChecked(state.status == integrations.ToolStatus.CONNECTED)
            toggle.setEnabled(False)
            if state.status == integrations.ToolStatus.CONNECTED:
                integrations.disconnect(tool)
            else:
                integrations.connect(tool)
        except (integrations.IntegrationsError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "操作失败", str(exc))
        finally:
            toggle.blockSignals(False)
            self.refresh_tool_rows()

    def _connect_all_tools(self) -> None:
        errors: list[str] = []
        for tool in integrations.TOOLS:
            try:
                if integrations.status(tool).status != integrations.ToolStatus.CONNECTED:
                    integrations.connect(tool)
            except (integrations.IntegrationsError, OSError, ValueError) as exc:
                errors.append(f"{integrations.TOOL_LABELS[tool]}：{exc}")
        self.refresh_tool_rows()
        if errors:
            QMessageBox.warning(self, "部分工具接通失败", "\n".join(errors))
