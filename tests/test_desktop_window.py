from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest = __import__("pytest")
pytest.importorskip("PySide6")

from PIL import Image  # noqa: E402

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.desktop_window import PetWindow  # noqa: E402
from petgen.pet_manifest import FrameAtlas, load_manifest  # noqa: E402


def _make_pet(tmp_path: Path):
    fw = fh = 8
    sprite = Image.new("RGBA", (16, 8), (0, 0, 0, 0))
    sprite.paste((200, 10, 20, 255), (0, 0, 8, 8))
    sprite.paste((30, 40, 50, 255), (8, 0, 16, 8))
    sprite.save(tmp_path / "sprite.png")
    manifest = {
        "id": "pet-render",
        "displayName": "render",
        "description": "d",
        "spritesheetPath": "sprite.png",
        "frame": {"width": fw, "height": fh, "columns": 2, "rows": 1},
        "animations": {
            "idle": {"frames": [0, 1], "fps": 2, "loop": True, "fallback": "idle"},
            "happy": {"frames": [1], "fps": 4, "loop": False, "fallback": "idle"},
        },
    }
    (tmp_path / "pet.json").write_text(json.dumps(manifest), encoding="utf-8")
    m = load_manifest(tmp_path)
    atlas = FrameAtlas.load(m.sprite_path, m.frame)
    return m, atlas


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-desktop"])


def _render(window: PetWindow) -> QImage:
    target = QImage(window.size(), QImage.Format_RGBA8888)
    target.fill(Qt.transparent)
    window.render(target)
    return target


def _assert_pixels_match(target: QImage, expected: Image.Image) -> None:
    assert target.width() == expected.width and target.height() == expected.height
    for y in range(expected.height):
        for x in range(expected.width):
            got = target.pixelColor(x, y)
            er, eg, eb, ea = expected.getpixel((x, y))
            assert (got.red(), got.green(), got.blue(), got.alpha()) == (er, eg, eb, ea)


def test_window_builds_pixmaps_and_masks_for_referenced_frames(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False)

    assert set(window._base_pixmaps) == {0, 1}  # noqa: SLF001
    assert set(window._base_bitmaps) == {0, 1}  # noqa: SLF001


def test_render_draws_expected_frame_pixels(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False)

    window.scheduler.play("idle")
    _assert_pixels_match(_render(window), atlas.crop(0))

    window.scheduler.play("happy")
    _assert_pixels_match(_render(window), atlas.crop(1))

    _render(window).save(str(tmp_path / "rendered_frame.png"))


def test_show_and_close_does_not_crash(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=True)

    window.show()
    QApplication.processEvents()
    window.close()


def _make_six_state_pet(tmp_path: Path):
    fw = fh = 48  # must exceed BADGE_SIZE (30) so the badge fits inside a frame
    cols, rows = 2, 3
    sprite = Image.new("RGBA", (cols * fw, rows * fh), (0, 0, 0, 0))
    colors = {
        0: (10, 10, 10, 255),
        1: (20, 20, 20, 255),
        2: (30, 30, 30, 255),
        3: (40, 40, 40, 255),
        4: (50, 50, 50, 255),
        5: (60, 60, 60, 255),
    }
    for idx, color in colors.items():
        r, c = divmod(idx, cols)
        sprite.paste(color, (c * fw, r * fh, (c + 1) * fw, (r + 1) * fh))
    sprite.save(tmp_path / "sprite.png")
    manifest = {
        "id": "pet-six",
        "displayName": "six",
        "description": "d",
        "spritesheetPath": "sprite.png",
        "frame": {"width": fw, "height": fh, "columns": cols, "rows": rows},
        "animations": {
            "idle": {"frames": [0], "fps": 1, "loop": True, "fallback": "idle"},
            "attentive": {"frames": [1], "fps": 1, "loop": False, "fallback": "idle"},
            "happy": {"frames": [2], "fps": 1, "loop": False, "fallback": "idle"},
            "busy": {"frames": [3], "fps": 1, "loop": True, "fallback": "idle"},
            "alert": {"frames": [4], "fps": 1, "loop": False, "fallback": "idle"},
            "error": {"frames": [5], "fps": 1, "loop": False, "fallback": "idle"},
        },
    }
    (tmp_path / "pet.json").write_text(json.dumps(manifest), encoding="utf-8")
    return load_manifest(tmp_path), FrameAtlas.load((tmp_path / "sprite.png"), load_manifest(tmp_path).frame)


def test_set_expression_cycles_all_six_states(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False, overlays=False)

    for name in ["idle", "attentive", "happy", "busy", "alert", "error"]:
        window.set_expression(name)
        assert window.scheduler.current_animation == name

    window.set_expression("definitely-not-a-state")
    assert window.scheduler.current_animation == "idle"


def test_left_click_emits_pet_clicked_and_keeps_window(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False, interactive=True)
    window.show()
    QApplication.processEvents()
    clicks: list[bool] = []
    window.pet_clicked.connect(lambda: clicks.append(True))

    QTest.mouseClick(window, Qt.LeftButton)

    assert clicks == [True]
    assert window.isVisible()
    window.close()


def test_right_click_interactive_emits_menu_signal_no_close(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False, interactive=True)
    window.show()
    QApplication.processEvents()
    menus: list[bool] = []
    window.pet_context_menu_requested.connect(lambda _pos: menus.append(True))

    QTest.mouseClick(window, Qt.RightButton)

    assert menus == [True]
    assert window.isVisible()
    window.close()


def test_right_click_non_interactive_closes(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False, interactive=False)
    window.show()
    QApplication.processEvents()

    QTest.mouseClick(window, Qt.RightButton)

    assert not window.isVisible()


def test_overlay_badge_changes_rendered_pixels(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)
    on = PetWindow(manifest, atlas, scale=1.0, passthrough=False, overlays=True, motion=False)
    off = PetWindow(manifest, atlas, scale=1.0, passthrough=False, overlays=False, motion=False)
    on.show()
    off.show()
    QApplication.processEvents()

    on.set_expression("happy")
    off.set_expression("happy")
    rendered_on = _render(on)
    rendered_off = _render(off)

    assert rendered_on.size() == rendered_off.size()
    # sanity: the sprite actually rendered (some opaque pixel present)
    assert any(
        rendered_off.pixelColor(x, y).alpha() > 0
        for y in range(rendered_off.height())
        for x in range(rendered_off.width())
    )
    diffs = 0
    for y in range(rendered_on.height()):
        for x in range(rendered_on.width()):
            if rendered_on.pixelColor(x, y).rgba() != rendered_off.pixelColor(x, y).rgba():
                diffs += 1
    assert diffs > 0
    on.close()
    off.close()


def test_celebrate_runs_and_clears_particles(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False)

    window.celebrate()
    assert window._particles  # noqa: SLF001

    for _ in range(60):  # offscreen QTimer won't tick; step the particle timer manually
        window._particle_tick()  # noqa: SLF001
    assert window._particles == []  # noqa: SLF001


def test_motion_off_holds_first_frame(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False, motion=False)

    window.set_expression("attentive")
    QApplication.processEvents()

    assert window.scheduler.current_animation == "attentive"
    assert window.scheduler.current_index() == 1


def test_set_scale_resizes_and_emits(qapp, tmp_path: Path) -> None:
    manifest, atlas = _make_six_state_pet(tmp_path)  # 48x48 frames
    window = PetWindow(manifest, atlas, scale=1.0, passthrough=False)
    assert window.width() == 48

    changes: list[float] = []
    window.scale_changed.connect(changes.append)
    window.set_scale(2.0)

    assert window.width() == 96 and window.height() == 96
    assert changes == [2.0]

    window.set_scale(2.0, persist=False)  # no change + no persist
    assert changes == [2.0]

    window.set_scale(10.0)  # clamped to 3.0
    assert window.width() == 144
    assert changes[-1] == 3.0
