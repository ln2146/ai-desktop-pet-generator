from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.tray import TrayController  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-tray-coord"])


def test_tray_menu_has_expected_items(qapp) -> None:
    tray = TrayController()
    labels = [a.text() for a in tray.menu().actions()]
    for expected in ["显示宠物", "宠物中心", "安静模式", "设置", "退出"]:
        assert expected in labels


def test_tray_menu_has_no_character_switcher(qapp) -> None:
    """The 'switch character' submenu was removed; character switching now lives
    in the library dialog, so the tray must not expose it (no dangling submenu)."""
    tray = TrayController()
    labels = [a.text() for a in tray.menu().actions()]
    assert "切换角色" not in labels
    assert not any(a.menu() is not None for a in tray.menu().actions())


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


def test_reload_pet_tolerates_corrupt_manifest(qapp, tmp_path: Path, monkeypatch) -> None:
    """A registered pet whose manifest is corrupt/missing must not crash the app.

    Regression: _reload_pet called load_manifest / FrameAtlas.load without a
    guard, so one bad library entry (e.g. a manually deleted pet dir) raised at
    startup and killed the whole app. It should now log, clear the broken
    selection, and continue with no pet window.
    """
    from PIL import Image, ImageDraw

    from petgen.coordinator import AppCoordinator
    from petgen.spritesheet import build_pet_assets

    monkeypatch.setenv("PETGEN_DATA_DIR", str(tmp_path))

    # Build a real pet and register it.
    src = tmp_path / "src.png"
    img = Image.new("RGBA", (960, 600), (0, 255, 0, 255))
    draw = ImageDraw.Draw(img)
    for row_index, count in enumerate((6, 4, 5)):
        top = [35, 220, 405][row_index]
        for col in range(count):
            cx = int(960 / count * (col + 0.5))
            draw.ellipse((cx - 34, top + 56, cx + 34, top + 134), fill=(236, 66, 74, 255))
    img.save(src)
    work = tmp_path / "work"
    paths = build_pet_assets(
        src, work, pet_id="pet-bad", description="d", model="m", prompt="p"
    )

    coord = AppCoordinator()
    try:
        record = coord.library.register_build(
            paths, pet_id="pet-bad", model="m", prompt="p", description="d"
        )
        coord.settings.set("pet.selected_id", record.id)
        # Corrupt the manifest so load_manifest raises.
        Path(record.manifest_path).write_text("{not valid json", encoding="utf-8")

        coord._reload_pet()  # must not raise

        assert coord.pet_window is None
        assert coord.settings.get("pet.selected_id") is None  # broken selection cleared
    finally:
        coord.bus.stop()
