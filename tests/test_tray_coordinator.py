from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.store import PetRecord  # noqa: E402
from petgen.tray import TrayController  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-tray-coord"])


def _record(pet_id: str, name: str) -> PetRecord:
    return PetRecord(
        id=pet_id,
        display_name=name,
        dir_path=f"/tmp/{pet_id}",
        sprite_path=f"/tmp/{pet_id}/sprite.png",
        manifest_path=f"/tmp/{pet_id}/pet.json",
        preview_path=None,
        model="m",
        prompt="p",
        description="d",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def test_tray_menu_has_expected_items(qapp) -> None:
    tray = TrayController()
    labels = [a.text() for a in tray.menu().actions()]
    for expected in ["显示宠物", "打开宠物库…", "安静模式", "设置…", "关于 PetGen", "退出"]:
        assert expected in labels
    assert any(a.text() == "切换角色" for a in tray.menu().actions())


def test_tray_set_characters_emits_selection(qapp) -> None:
    tray = TrayController()
    tray.set_characters([_record("a", "猫"), _record("b", "熊猫")], selected_id="a")
    submenu = tray.character_menu()
    assert submenu is not None
    items = [a for a in submenu.actions() if a.text()]
    assert [a.text() for a in items] == ["猫", "熊猫"]
    assert items[0].isChecked() is True

    got: list[str] = []
    tray.character_selected.connect(got.append)
    items[1].trigger()
    assert got == ["b"]


def test_tray_quiet_and_show_actions_toggle(qapp) -> None:
    tray = TrayController()
    quiets: list[bool] = []
    tray.quiet_toggled.connect(quiets.append)
    quiet_action = next(a for a in tray.menu().actions() if a.text() == "安静模式")
    quiet_action.trigger()
    assert quiets == [True]


def test_coordinator_bootstrap_does_not_crash(qapp, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))
    from petgen.coordinator import AppCoordinator

    coord = AppCoordinator()
    coord.bootstrap()
    try:
        assert coord.tray is not None
        assert coord.bus is not None
    finally:
        coord.bus.stop()
