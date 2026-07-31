from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen import i18n  # noqa: E402
from petgen.library_dialog import LibraryDialog  # noqa: E402
from petgen.reminder_editor import ReminderEditorDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-i18n"])


def test_dynamic_labels_follow_active_language(qapp) -> None:
    assert i18n.install_translator(qapp, "en")

    assert i18n.current_language() == "en"
    assert i18n.interaction_style_label("moe-pet", "萌宠风") == "Soft Pet"
    assert i18n.interaction_style_label("steady-senior", "沉稳男声") == "Steady Senior"
    assert i18n.recurrence_label("weekdays_full") == "Weekdays (Mon-Fri)"
    assert i18n.weekday_short_label(0) == "Mon"
    assert i18n.tool_status_label("✅ 已接通") == "✅ Connected"

    assert i18n.install_translator(qapp, "zh_CN")
    assert i18n.current_language() == "zh_CN"
    assert i18n.interaction_style_label("moe-pet", "萌宠风") == "萌宠风"
    assert i18n.recurrence_label("weekdays_full") == "工作日 (周一至周五)"


def test_english_ui_uses_translated_dynamic_labels(qapp) -> None:
    assert i18n.install_translator(qapp, "en")

    reminder = ReminderEditorDialog()
    recurrence_items = [
        reminder.recurrence.itemText(i) for i in range(reminder.recurrence.count())
    ]
    weekday_items = [box.text() for box in reminder._weekday_boxes]  # noqa: SLF001

    assert "No repeat" in recurrence_items
    assert "Weekdays (Mon-Fri)" in recurrence_items
    assert "不重复" not in recurrence_items
    assert weekday_items[:2] == ["Mon", "Tue"]

    library = LibraryDialog()
    style_items = [
        library._interaction_style_combo.itemText(i)  # noqa: SLF001
        for i in range(library._interaction_style_combo.count())  # noqa: SLF001
    ]

    assert any("Soft Pet" in item for item in style_items)
    assert any("Steady Senior" in item for item in style_items)
    assert not any("萌宠风" in item or "沉稳男声" in item for item in style_items)


def test_missing_translation_file_logs_and_keeps_source_language(
    qapp, tmp_path, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(i18n, "_I18N_DIR", tmp_path)

    assert not i18n.install_translator(qapp, "en")

    assert i18n.current_language() == "zh_CN"
    assert "failed to load translation file" in caplog.text
