from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from petgen.datadir import pets_root
from petgen.pet_manifest import ManifestError, load_manifest
from petgen.store import PetRecord, PetRegistry


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unique_id(registry: PetRegistry, base_id: str) -> str:
    if not registry.get(base_id):
        return base_id
    suffix = 2
    while registry.get(f"{base_id}-{suffix}"):
        suffix += 1
    return f"{base_id}-{suffix}"


def _copy_assets(src_dir: Path, target_dir: Path) -> tuple[Path, Path, Path | None]:
    target_dir.mkdir(parents=True, exist_ok=True)
    sprite_src = src_dir / "sprite.png"
    manifest_src = src_dir / "pet.json"
    if not sprite_src.is_file():
        raise ManifestError(f"sprite.png not found in {src_dir}")
    if not manifest_src.is_file():
        raise ManifestError(f"pet.json not found in {src_dir}")
    sprite_dst = target_dir / "sprite.png"
    manifest_dst = target_dir / "pet.json"
    shutil.copy2(sprite_src, sprite_dst)
    shutil.copy2(manifest_src, manifest_dst)
    preview_dst: Path | None = None
    preview_src = src_dir / "preview.png"
    if preview_src.is_file():
        preview_dst = target_dir / "preview.png"
        shutil.copy2(preview_src, preview_dst)
    return sprite_dst, manifest_dst, preview_dst


class PetLibrary:
    """High-level managed pet collection: copy assets + index them in SQLite."""

    def __init__(self, registry: PetRegistry, root: Path | None = None) -> None:
        self._registry = registry
        self._root = root or pets_root()

    @property
    def root(self) -> Path:
        return self._root

    def register_build(
        self,
        output_paths: dict[str, Path],
        *,
        pet_id: str,
        model: str,
        prompt: str,
        description: str,
    ) -> PetRecord:
        """Copy a freshly generated pet's assets into the library and register it."""
        manifest_path = Path(output_paths["manifest"])
        display_name = _read_display_name(manifest_path)
        pet_id = _unique_id(self._registry, pet_id)
        src_dir = manifest_path.parent
        sprite_dst, manifest_dst, preview_dst = _copy_assets(src_dir, self._root / pet_id)
        now = _utcnow()
        record = PetRecord(
            id=pet_id,
            display_name=display_name,
            dir_path=str(self._root / pet_id),
            sprite_path=str(sprite_dst),
            manifest_path=str(manifest_dst),
            preview_path=str(preview_dst) if preview_dst else None,
            model=model,
            prompt=prompt,
            description=description,
            created_at=now,
            updated_at=now,
        )
        self._registry.register(record)
        return record

    def import_existing_dir(self, src: Path) -> PetRecord:
        """Validate + copy an existing pet directory (e.g. an old outputs/ run)."""
        src = Path(src).expanduser().resolve()
        manifest = load_manifest(src)  # validates manifest + sprite
        base_id = manifest.id or src.name
        pet_id = _unique_id(self._registry, base_id)
        sprite_dst, manifest_dst, preview_dst = _copy_assets(src, self._root / pet_id)
        now = _utcnow()
        record = PetRecord(
            id=pet_id,
            display_name=manifest.display_name or src.name,
            dir_path=str(self._root / pet_id),
            sprite_path=str(sprite_dst),
            manifest_path=str(manifest_dst),
            preview_path=str(preview_dst) if preview_dst else None,
            model=_read_generation_field(manifest.sprite_path.parent / "pet.json", "model"),
            prompt=_read_generation_field(manifest.sprite_path.parent / "pet.json", "prompt"),
            description=manifest.description,
            created_at=now,
            updated_at=now,
        )
        self._registry.register(record)
        return record

    def list_pets(self) -> list[PetRecord]:
        return self._registry.list_pets()

    def get(self, pet_id: str) -> PetRecord | None:
        return self._registry.get(pet_id)

    def delete_pet(self, pet_id: str) -> bool:
        record = self._registry.get(pet_id)
        deleted = self._registry.delete(pet_id)
        if record:
            shutil.rmtree(record.dir_path, ignore_errors=True)
        return deleted

    def rename(self, pet_id: str, display_name: str) -> bool:
        new_name = display_name.strip()
        if not new_name:
            return False
        record = self._registry.get(pet_id)
        if record is None:
            return False
        manifest_path = Path(record.manifest_path)
        if manifest_path.is_file():
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    raw["displayName"] = new_name
                    manifest_path.write_text(
                        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
            except (OSError, ValueError):
                pass
        return self._registry.rename(pet_id, new_name)

    def thumbnail_path(self, record: PetRecord) -> Path | None:
        if record.preview_path and Path(record.preview_path).is_file():
            return Path(record.preview_path)
        if Path(record.sprite_path).is_file():
            return Path(record.sprite_path)
        return None

    def resolve_selected(self, settings) -> PetRecord | None:
        selected_id = settings.get("pet.selected_id")
        if selected_id:
            record = self._registry.get(selected_id)
            if record is not None:
                return record
        pets = self._registry.list_pets()
        return pets[-1] if pets else None

    def select(self, settings, pet_id: str) -> None:
        settings.set("pet.selected_id", pet_id)


def _read_display_name(manifest_path: Path) -> str:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"failed to read {manifest_path}: {exc}") from exc
    name = raw.get("displayName") if isinstance(raw, dict) else None
    return str(name) if name else manifest_path.parent.name


def _read_generation_field(manifest_path: Path, field: str) -> str:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(raw, dict):
        return ""
    generation = raw.get("_generation")
    if not isinstance(generation, dict):
        return ""
    value = generation.get(field)
    return str(value) if value is not None else ""
