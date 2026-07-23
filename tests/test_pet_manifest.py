from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from petgen.pet_manifest import (
    FrameAtlas,
    FrameSpec,
    ManifestError,
    load_manifest,
)

OMIT = object()

DEFAULT_ANIMS_2 = {
    "idle": {"frames": [0, 1], "fps": 2.0, "loop": True, "fallback": "idle"},
    "happy": {"frames": [1], "fps": 4.0, "loop": False, "fallback": "idle"},
}


def _cell_color(index: int) -> tuple[int, int, int, int]:
    return ((index * 40 + 30) % 256, (index * 80 + 50) % 256, (index * 120 + 70) % 256, 255)


def make_sprite(cols: int, rows: int, fw: int, fh: int) -> Image.Image:
    image = Image.new("RGBA", (cols * fw, rows * fh), (0, 0, 0, 0))
    for idx in range(cols * rows):
        r, c = divmod(idx, cols)
        box = (c * fw, r * fh, (c + 1) * fw, (r + 1) * fh)
        image.paste(_cell_color(idx), box)
    return image


def make_pet_dir(
    tmp_path: Path,
    *,
    cols: int = 2,
    rows: int = 1,
    fw: int = 10,
    fh: int = 10,
    animations=DEFAULT_ANIMS_2,
    drop_keys: set[str] | None = None,
    frame: dict | None = None,
    with_sprite: bool = True,
    sprite_size: tuple[int, int] | None = None,
) -> Path:
    sprite = make_sprite(cols, rows, fw, fh) if sprite_size is None else Image.new(
        "RGBA", sprite_size, (1, 2, 3, 255)
    )
    if with_sprite:
        sprite.save(tmp_path / "sprite.png")
    manifest = {
        "id": "pet-x",
        "displayName": "X",
        "description": "d",
        "spritesheetPath": "sprite.png",
        "frame": frame or {"width": fw, "height": fh, "columns": cols, "rows": rows},
    }
    if animations is not OMIT:
        manifest["animations"] = animations
    for key in drop_keys or set():
        manifest.pop(key, None)
    import json

    (tmp_path / "pet.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_load_manifest_from_directory(tmp_path: Path) -> None:
    pet_dir = make_pet_dir(tmp_path)

    manifest = load_manifest(pet_dir)

    assert manifest.id == "pet-x"
    assert manifest.display_name == "X"
    assert manifest.frame == FrameSpec(10, 10, 2, 1)
    assert manifest.sprite_path.is_absolute()
    assert manifest.sprite_path == (tmp_path / "sprite.png").resolve()
    assert manifest.animations["idle"].frames == (0, 1)
    assert manifest.animations["happy"].loop is False


def test_load_manifest_from_file_path(tmp_path: Path) -> None:
    make_pet_dir(tmp_path)

    manifest = load_manifest(tmp_path / "pet.json")

    assert manifest.manifest_dir == tmp_path
    assert manifest.sprite_path == (tmp_path / "sprite.png").resolve()


def test_load_manifest_missing_top_level_key(tmp_path: Path) -> None:
    make_pet_dir(tmp_path, drop_keys={"spritesheetPath"})
    with pytest.raises(ManifestError, match="spritesheetPath"):
        load_manifest(tmp_path)


def test_load_manifest_missing_frame_subkey(tmp_path: Path) -> None:
    make_pet_dir(tmp_path, frame={"width": 10, "height": 10, "rows": 1})
    with pytest.raises(ManifestError, match="columns"):
        load_manifest(tmp_path)


def test_load_manifest_missing_sprite_file(tmp_path: Path) -> None:
    make_pet_dir(tmp_path, with_sprite=False)
    with pytest.raises(ManifestError, match="sprite sheet not found"):
        load_manifest(tmp_path)


def test_load_manifest_out_of_range_animation_index(tmp_path: Path) -> None:
    make_pet_dir(tmp_path, animations={"idle": {"frames": [0, 99], "fps": 1, "loop": True, "fallback": "idle"}})
    with pytest.raises(ManifestError, match="out-of-range"):
        load_manifest(tmp_path)


def test_load_manifest_falls_back_to_default_animations(tmp_path: Path) -> None:
    make_pet_dir(tmp_path, cols=8, rows=9, fw=2, fh=2, animations=OMIT)

    manifest = load_manifest(tmp_path)

    assert "idle" in manifest.animations
    assert "happy" in manifest.animations
    assert manifest.animations["idle"].frames[0] == 0


def test_load_manifest_nonexistent_path(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="no pet manifest"):
        load_manifest(tmp_path / "does-not-exist")


def test_initial_animation_prefers_idle(tmp_path: Path) -> None:
    manifest = load_manifest(make_pet_dir(tmp_path))
    assert manifest.initial_animation() == "idle"


def test_initial_animation_without_idle_uses_first(tmp_path: Path) -> None:
    anims = {
        "happy": {"frames": [0], "fps": 1, "loop": False, "fallback": "happy"},
        "busy": {"frames": [1], "fps": 1, "loop": True, "fallback": "busy"},
    }
    manifest = load_manifest(make_pet_dir(tmp_path, animations=anims))
    assert manifest.initial_animation() == "happy"


def test_frame_atlas_crop_matches_manual_crop(tmp_path: Path) -> None:
    spec = FrameSpec(10, 10, 2, 1)
    sprite = make_sprite(2, 1, 10, 10)
    sprite_path = tmp_path / "sprite.png"
    sprite.save(sprite_path)
    atlas = FrameAtlas.load(sprite_path, spec)

    for idx in (0, 1):
        r, c = divmod(idx, spec.columns)
        expected = sprite.crop((c * 10, r * 10, (c + 1) * 10, (r + 1) * 10))
        assert atlas.crop(idx).tobytes() == expected.tobytes()


def test_frame_atlas_rejects_size_mismatch(tmp_path: Path) -> None:
    spec = FrameSpec(10, 10, 2, 1)
    wrong = tmp_path / "wrong.png"
    Image.new("RGBA", (99, 99), (0, 0, 0, 0)).save(wrong)
    with pytest.raises(ManifestError, match="expected 20x10"):
        FrameAtlas.load(wrong, spec)


def test_frame_atlas_crop_out_of_range(tmp_path: Path) -> None:
    spec = FrameSpec(10, 10, 2, 1)
    sprite_path = tmp_path / "sprite.png"
    make_sprite(2, 1, 10, 10).save(sprite_path)
    atlas = FrameAtlas.load(sprite_path, spec)
    with pytest.raises(ManifestError):
        atlas.crop(5)


def test_default_animations_not_shared_with_manifest(tmp_path: Path) -> None:
    """Mutating a built manifest's animations must not leak into the global map."""
    import json

    from petgen.spritesheet import DEFAULT_ANIMATIONS, build_pet_assets

    src = tmp_path / "src.png"
    _make_source(src)
    result = build_pet_assets(
        src, tmp_path / "pet", pet_id="p", description="d", model="m", prompt="p"
    )
    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
    idle_before = list(DEFAULT_ANIMATIONS["idle"]["frames"])

    manifest["animations"]["idle"]["frames"].append(999)
    manifest["animations"]["POISON"] = {}

    assert DEFAULT_ANIMATIONS["idle"]["frames"] == idle_before
    assert "POISON" not in DEFAULT_ANIMATIONS


def _make_source(path: Path) -> None:
    from PIL import ImageDraw

    img = Image.new("RGBA", (960, 600), (0, 255, 0, 255))
    draw = ImageDraw.Draw(img)
    for row_index, count in enumerate((6, 4, 5)):
        top = [35, 220, 405][row_index]
        for col in range(count):
            cx = int(960 / count * (col + 0.5))
            draw.ellipse((cx - 34, top + 56, cx + 34, top + 134), fill=(236, 66, 74, 255))
    img.save(path)
