from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from petgen.library import PetLibrary
from petgen.store import PetRegistry, SettingsStore


def _write_pet_dir(
    base: Path,
    *,
    pet_id: str = "pet-x",
    display_name: str = "测试宠物",
    with_preview: bool = True,
) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": pet_id,
        "displayName": display_name,
        "description": "desc",
        "spritesheetPath": "sprite.png",
        "frame": {"width": 8, "height": 8, "columns": 2, "rows": 1},
        "animations": {
            "idle": {"frames": [0, 1], "fps": 1, "loop": True, "fallback": "idle"},
        },
        "_generation": {"model": "m", "prompt": "p"},
    }
    (base / "pet.json").write_text(json.dumps(manifest), encoding="utf-8")
    Image.new("RGBA", (16, 8), (200, 10, 20, 255)).save(base / "sprite.png")
    if with_preview:
        Image.new("RGBA", (8, 8), (30, 40, 50, 255)).save(base / "preview.png")
    return base


def _make_library(tmp_path: Path) -> tuple[PetLibrary, PetRegistry, SettingsStore]:
    db = tmp_path / "db.sqlite"
    registry = PetRegistry(db)
    settings = SettingsStore(db)
    library = PetLibrary(registry, root=tmp_path / "managed")
    return library, registry, settings


def test_register_build_copies_and_indexes(tmp_path: Path) -> None:
    out = tmp_path / "build_out"
    _write_pet_dir(out, pet_id="gen-1", display_name="生成猫")
    library, registry, _ = _make_library(tmp_path)

    record = library.register_build(
        {"sprite": out / "sprite.png", "manifest": out / "pet.json", "preview": out / "preview.png"},
        pet_id="gen-1",
        model="m",
        prompt="p",
        description="d",
    )

    assert record.id == "gen-1"
    assert record.display_name == "生成猫"
    assert Path(record.sprite_path).is_file()
    assert Path(record.manifest_path).is_file()
    assert Path(record.preview_path).is_file()
    assert Path(record.dir_path) == library.root / "gen-1"
    assert registry.count() == 1


def test_import_existing_dir_copies_and_loads(tmp_path: Path) -> None:
    src = _write_pet_dir(tmp_path / "old_run", pet_id="old", display_name="旧宠")
    library, registry, _ = _make_library(tmp_path)

    record = library.import_existing_dir(src)

    assert record.id == "old"
    assert record.model == "m"
    assert record.prompt == "p"
    assert registry.get("old") is not None
    assert Path(record.sprite_path).is_file()


def test_duplicate_id_gets_suffix(tmp_path: Path) -> None:
    src1 = _write_pet_dir(tmp_path / "run1", pet_id="dup", display_name="一")
    src2 = _write_pet_dir(tmp_path / "run2", pet_id="dup", display_name="二")
    library, registry, _ = _make_library(tmp_path)

    first = library.import_existing_dir(src1)
    second = library.import_existing_dir(src2)

    assert first.id == "dup"
    assert second.id == "dup-2"
    assert registry.count() == 2


def test_delete_pet_removes_row_and_dir(tmp_path: Path) -> None:
    out = tmp_path / "build_out"
    _write_pet_dir(out, pet_id="del-me")
    library, registry, _ = _make_library(tmp_path)
    record = library.register_build(
        {"manifest": out / "pet.json"}, pet_id="del-me", model="m", prompt="p", description="d"
    )
    managed_dir = Path(record.dir_path)
    assert managed_dir.is_dir()

    assert library.delete_pet("del-me") is True

    assert registry.get("del-me") is None
    assert not managed_dir.exists()
    assert library.delete_pet("del-me") is False


def test_thumbnail_path_prefers_preview_then_sprite(tmp_path: Path) -> None:
    out = tmp_path / "build_out"
    _write_pet_dir(out, pet_id="thumb", with_preview=True)
    library, _, _ = _make_library(tmp_path)
    record = library.register_build(
        {"manifest": out / "pet.json"}, pet_id="thumb", model="m", prompt="p", description="d"
    )
    assert library.thumbnail_path(record) == Path(record.preview_path)

    Path(record.preview_path).unlink()
    assert library.thumbnail_path(record) == Path(record.sprite_path)


def test_resolve_selected_falls_back_to_most_recent(tmp_path: Path) -> None:
    library, _, settings = _make_library(tmp_path)
    a = _write_pet_dir(tmp_path / "a", pet_id="a")
    b = _write_pet_dir(tmp_path / "b", pet_id="b")
    library.import_existing_dir(a)
    library.import_existing_dir(b)

    # no selection recorded → most recent (last by created_at) is returned
    settings.set("pet.selected_id", None)
    resolved = library.resolve_selected(settings)
    assert resolved is not None and resolved.id in {"a", "b"}

    # stale selection id falls back to most recent
    settings.set("pet.selected_id", "ghost")
    assert library.resolve_selected(settings) is not None

    # valid selection wins
    settings.set("pet.selected_id", "a")
    assert library.resolve_selected(settings).id == "a"


def test_resolve_selected_empty_library(tmp_path: Path) -> None:
    library, _, settings = _make_library(tmp_path)
    assert library.resolve_selected(settings) is None


def test_rename_updates_registry_and_manifest(tmp_path: Path) -> None:
    import json

    out = tmp_path / "build_out"
    _write_pet_dir(out, pet_id="rename-me", display_name="旧名")
    library, registry, _ = _make_library(tmp_path)
    library.register_build(
        {"manifest": out / "pet.json"}, pet_id="rename-me", model="m", prompt="p", description="d"
    )

    assert library.rename("rename-me", "  新名字  ") is True
    assert registry.get("rename-me").display_name == "新名字"
    manifest = json.loads(Path(registry.get("rename-me").manifest_path).read_text(encoding="utf-8"))
    assert manifest["displayName"] == "新名字"

    assert library.rename("rename-me", "   ") is False  # blank name rejected
    assert library.rename("ghost", "x") is False  # unknown id


def test_register_build_missing_sprite_raises(tmp_path: Path) -> None:
    out = tmp_path / "broken"
    out.mkdir()
    (out / "pet.json").write_text("{}", encoding="utf-8")
    library, _, _ = _make_library(tmp_path)
    from petgen.pet_manifest import ManifestError

    with pytest.raises(ManifestError):
        library.register_build(
            {"manifest": out / "pet.json"}, pet_id="broken", model="m", prompt="p", description="d"
        )
