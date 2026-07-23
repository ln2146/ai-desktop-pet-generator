from __future__ import annotations

from pathlib import Path

from petgen.store import AiEventStore, PetRecord, PetRegistry, SettingsStore


def _record(pet_id: str, tmp_path: Path, *, display_name: str | None = None) -> PetRecord:
    pet_dir = tmp_path / "pets" / pet_id
    pet_dir.mkdir(parents=True, exist_ok=True)
    return PetRecord(
        id=pet_id,
        display_name=display_name or f"宠物 {pet_id}",
        dir_path=str(pet_dir),
        sprite_path=str(pet_dir / "sprite.png"),
        manifest_path=str(pet_dir / "pet.json"),
        preview_path=str(pet_dir / "preview.png"),
        model="test-model",
        prompt="test prompt",
        description="desc",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def test_settings_round_trip_and_default(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "db.sqlite")
    try:
        assert store.get("missing", "fallback") == "fallback"
        store.set("pet.scale", 1.5)
        store.set("ai.click_chat", True)
        store.set("pet.personality", "傲娇小猫")
        assert store.get("pet.scale") == 1.5
        assert store.get("ai.click_chat") is True
        assert store.get("pet.personality") == "傲娇小猫"
        store.set("pet.scale", 2.0)
        assert store.get("pet.scale") == 2.0
    finally:
        store.close()


def test_settings_get_all_and_set_many(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "db.sqlite")
    try:
        store.set_many({"a": 1, "b": [1, 2], "c": "中文"})
        assert store.get_all() == {"a": 1, "b": [1, 2], "c": "中文"}
    finally:
        store.close()


def test_schema_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    first = SettingsStore(path)
    first.set("k", "v")
    first.close()
    second = SettingsStore(path)
    try:
        assert second.get("k") == "v"
    finally:
        second.close()


def test_registry_register_list_get_delete(tmp_path: Path) -> None:
    reg = PetRegistry(tmp_path / "db.sqlite")
    try:
        assert reg.count() == 0
        reg.register(_record("pet-a", tmp_path))
        reg.register(_record("pet-b", tmp_path))
        assert reg.count() == 2
        assert [p.id for p in reg.list_pets()] == ["pet-a", "pet-b"]
        got = reg.get("pet-a")
        assert got is not None and got.display_name == "宠物 pet-a"
        assert reg.get("nope") is None
        assert reg.delete("pet-a") is True
        assert reg.delete("pet-a") is False
        assert reg.count() == 1
    finally:
        reg.close()


def test_registry_register_replaces_on_same_id(tmp_path: Path) -> None:
    reg = PetRegistry(tmp_path / "db.sqlite")
    try:
        rec = _record("pet-x", tmp_path, display_name="旧名字")
        reg.register(rec)
        reg.register(
            rec.__class__(
                id="pet-x",
                display_name="新名字",
                dir_path=rec.dir_path,
                sprite_path=rec.sprite_path,
                manifest_path=rec.manifest_path,
                preview_path=rec.preview_path,
                model=rec.model,
                prompt=rec.prompt,
                description=rec.description,
                created_at=rec.created_at,
                updated_at="2026-02-02T00:00:00Z",
            )
        )
        assert reg.count() == 1
        assert reg.get("pet-x").display_name == "新名字"
    finally:
        reg.close()


def test_ai_event_store_append_dedups_and_stats(tmp_path: Path) -> None:
    store = AiEventStore(tmp_path / "db.sqlite")
    try:
        event = {
            "id": "e1",
            "kind": "task_completed",
            "title": "done",
            "detail": None,
            "source": "manual",
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert store.append(event) is True
        assert store.append(event) is False  # duplicate id ignored
        assert store.append({**event, "id": "e2", "kind": "ai_thinking"}) is True
        stats = store.stats()
        assert stats["total"] == 2
        assert stats["by_kind"] == {"task_completed": 1, "ai_thinking": 1}
    finally:
        store.close()


def test_stores_share_one_connection(tmp_path: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "shared.sqlite"))
    conn.row_factory = sqlite3.Row
    settings = SettingsStore(conn)
    registry = PetRegistry(conn)
    try:
        settings.set("pet.selected_id", "pet-a")
        registry.register(_record("pet-a", tmp_path))
        # a fresh reader on the same file sees both writes
        reader = SettingsStore(tmp_path / "shared.sqlite")
        try:
            assert reader.get("pet.selected_id") == "pet-a"
            assert PetRegistry(tmp_path / "shared.sqlite").count() == 1
        finally:
            reader.close()
    finally:
        settings.close()
        registry.close()
        conn.close()
