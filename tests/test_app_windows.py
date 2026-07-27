from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PIL import Image  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from petgen.bubble import BubbleWindow  # noqa: E402
from petgen.library_dialog import LibraryDialog  # noqa: E402
from petgen.settings_dialog import SettingsDialog  # noqa: E402
from petgen.store import PetRecord, SettingsStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-app-windows"])


# --- bubble -----------------------------------------------------------------


def test_bubble_short_message_has_no_close_button(qapp) -> None:
    bubble = BubbleWindow()
    bubble.show_message("hi")
    bubble.show()
    QApplication.processEvents()
    assert not bubble._close_button.isVisible()  # noqa: SLF001
    bubble.hide_now()


def test_bubble_long_message_has_no_button_row(qapp) -> None:
    bubble = BubbleWindow()
    bubble.show_message("这是一段足够长的消息，用来验证超过阈值时关闭按钮会显示出来，应该够长了。")
    bubble.show()
    QApplication.processEvents()
    assert not bubble._close_button.isVisible()  # noqa: SLF001
    assert not bubble._button_bar.isVisible()  # noqa: SLF001
    bubble.hide_now()


def test_bubble_actions_show_button_row(qapp) -> None:
    bubble = BubbleWindow()
    bubble.show_message("提醒", actions=[("完成", lambda: None)])
    bubble.show()
    QApplication.processEvents()
    assert not bubble._close_button.isVisible()  # noqa: SLF001
    assert bubble._button_bar.isVisible()  # noqa: SLF001
    bubble.hide_now()


def test_bubble_hide_now_emits_dismissed(qapp) -> None:
    bubble = BubbleWindow()
    bubble.show_message("x")
    dismissed: list[bool] = []
    bubble.dismissed.connect(lambda: dismissed.append(True))
    bubble.hide_now()
    assert dismissed == [True]
    assert not bubble.isVisible()


def test_bubble_timer_dismisses(qapp) -> None:
    bubble = BubbleWindow()
    dismissed: list[bool] = []
    bubble.dismissed.connect(lambda: dismissed.append(True))
    bubble.show_message("x", timeout_ms=30)
    bubble._timer.timeout.emit()  # noqa: SLF001 - offscreen timers don't tick
    assert dismissed == [True]


# --- settings dialog --------------------------------------------------------


def test_settings_dialog_round_trip(qapp, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "db.sqlite")
    try:
        dlg = SettingsDialog(store)
        dlg.ai_api_key.setText("sk-test")
        dlg.ai_base_url.setText("https://example.test/v1")
        dlg.ai_image_model.setText("img-model")
        dlg.ai_text_model.setText("txt-model")
        dlg.pet_scale.setValue(2.25)
        dlg.pet_motion.setChecked(False)
        dlg.pet_sound.setChecked(True)
        dlg.pet_click_chat.setChecked(True)
        dlg.apply_values()

        dlg2 = SettingsDialog(store)
        assert dlg2.ai_api_key.text() == "sk-test"
        assert dlg2.ai_base_url.text() == "https://example.test/v1"
        assert dlg2.ai_image_model.text() == "img-model"
        assert dlg2.ai_text_model.text() == "txt-model"
        assert dlg2.pet_scale.value() == pytest.approx(2.25)
        assert dlg2.pet_motion.isChecked() is False
        assert dlg2.pet_sound.isChecked() is True
        assert dlg2.pet_click_chat.isChecked() is True
    finally:
        store.close()


def test_settings_dialog_applied_signal(qapp, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "db.sqlite")
    try:
        dlg = SettingsDialog(store)
        applied: list[bool] = []
        dlg.applied.connect(lambda: applied.append(True))
        dlg._save()  # noqa: SLF001
        assert applied == [True]
    finally:
        store.close()


# --- library dialog ---------------------------------------------------------


def _record(pet_id: str, tmp_path: Path, name: str) -> PetRecord:
    d = tmp_path / "managed" / pet_id
    d.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), (120, 120, 120, 255)).save(d / "sprite.png")
    Image.new("RGBA", (8, 8), (200, 200, 200, 255)).save(d / "preview.png")
    (d / "pet.json").write_text(
        json.dumps({"id": pet_id, "spritesheetPath": "sprite.png"}), encoding="utf-8"
    )
    return PetRecord(
        id=pet_id,
        display_name=name,
        dir_path=str(d),
        sprite_path=str(d / "sprite.png"),
        manifest_path=str(d / "pet.json"),
        preview_path=str(d / "preview.png"),
        model="m",
        prompt="p",
        description="d",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _buttons(card, text: str):
    return [b for b in card.findChildren(QPushButton) if b.text() == text]


def test_library_dialog_refresh_renders_cards(qapp, tmp_path: Path) -> None:
    dlg = LibraryDialog()
    pets = [_record("a", tmp_path, "猫"), _record("b", tmp_path, "熊猫")]
    dlg.refresh(pets, selected_id="a")
    assert len(dlg._cards) == 2  # noqa: SLF001


def test_library_dialog_select_and_delete_signals(qapp, tmp_path: Path) -> None:
    dlg = LibraryDialog()
    pets = [_record("a", tmp_path, "猫"), _record("b", tmp_path, "熊猫")]
    dlg.refresh(pets, selected_id=None)
    selected: list[str] = []
    deleted: list[str] = []
    dlg.pet_selected.connect(selected.append)
    dlg.delete_requested.connect(deleted.append)

    card_a = dlg._cards[0]  # noqa: SLF001
    QTest.mouseClick(_buttons(card_a, "选择")[0], Qt.LeftButton, Qt.NoModifier)
    QTest.mouseClick(_buttons(card_a, "删除")[0], Qt.LeftButton, Qt.NoModifier)

    assert selected == ["a"]
    assert deleted == ["a"]


def test_library_dialog_set_progress_toggles_create(qapp) -> None:
    dlg = LibraryDialog()
    dlg.set_progress("正在生成形象…")
    assert not dlg._create_btn.isEnabled()  # noqa: SLF001
    assert dlg._progress.text() == "正在生成形象…"  # noqa: SLF001
    dlg.set_progress("")
    assert dlg._create_btn.isEnabled()  # noqa: SLF001


def test_library_dialog_style_controls_emit_values(qapp) -> None:
    from petgen.interaction_style import load_styles

    dlg = LibraryDialog()
    assert set(dlg._interaction_style_keys) == set(load_styles())  # noqa: SLF001

    styles: list[str] = []
    previews: list[bool] = []
    dlg.interaction_style_changed.connect(styles.append)
    dlg.preview_style_requested.connect(lambda: previews.append(True))

    dlg.set_interaction_style_value("tsundere")
    assert dlg._interaction_style_combo.currentData() == "tsundere"  # noqa: SLF001
    assert styles == []

    dlg._interaction_style_combo.setCurrentIndex(dlg._interaction_style_keys.index("moe-pet"))  # noqa: SLF001
    preview_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "▶ 试听")
    QTest.mouseClick(preview_btn, Qt.LeftButton, Qt.NoModifier)

    assert styles == ["moe-pet"]
    assert previews == [True]


def test_library_dialog_voice_config_tracks_current_style(qapp) -> None:
    dlg = LibraryDialog()
    providers: list[str] = []
    refs: list[tuple[str, str]] = []
    dlg.voice_provider_changed.connect(providers.append)
    dlg.fish_reference_id_changed.connect(lambda style_id, ref_id: refs.append((style_id, ref_id)))

    dlg.set_voice_config(
        provider="fish",
        fish_api_key="fish-key",
        fish_reference_ids={"moe-pet": "pet-voice", "tsundere": "tsun-voice"},
    )
    assert dlg._voice_provider_combo.currentData() == "fish"  # noqa: SLF001
    assert dlg._fish_api_key.text() == "fish-key"  # noqa: SLF001

    dlg.set_interaction_style_value("tsundere")
    assert dlg._fish_reference_id.text() == "tsun-voice"  # noqa: SLF001

    dlg._fish_reference_id.setText("updated")  # noqa: SLF001
    dlg._on_fish_reference_id_changed()  # noqa: SLF001

    dlg._voice_provider_combo.setCurrentIndex(0)  # noqa: SLF001
    assert providers == ["edge"]
    assert refs == [("tsundere", "updated")]
