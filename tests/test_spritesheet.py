from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from petgen.spritesheet import (
    SpriteSpec,
    build_pet_assets,
    compose_sprite_sheet,
    crop_premium_action_rows,
)


def test_crop_and_compose_premium_action_rows(tmp_path: Path) -> None:
    source = make_source()
    rows = crop_premium_action_rows(source)
    assert [len(row) for row in rows] == [6, 4, 5]

    sprite = compose_sprite_sheet(rows)
    spec = SpriteSpec()
    assert sprite.size == (spec.frame_width * spec.columns, spec.frame_height * spec.rows)

    for frame_index in [0, 5, 24, 27, 32, 36, 40, 48, 56, 64]:
        frame = crop_frame(sprite, frame_index, spec)
        assert frame.getbbox() is not None

    first = crop_frame(sprite, 0, spec)
    bbox = first.getbbox()
    assert bbox is not None
    assert bbox[0] >= 6
    assert bbox[2] <= spec.frame_width - 6
    assert bbox[1] >= 4
    assert bbox[3] <= spec.frame_height - 4


def test_build_pet_assets_writes_manifest_and_preview(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    make_source().save(source_path)
    result = build_pet_assets(
        source_path,
        tmp_path / "pet",
        pet_id="pet-test",
        display_name="测试宠物",
        description="测试描述",
        model="test-model",
        prompt="test prompt",
    )

    assert result["sprite"].exists()
    assert result["manifest"].exists()
    assert result["preview"].exists()

    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
    assert manifest["id"] == "pet-test"
    assert manifest["displayName"] == "测试宠物"
    assert manifest["frame"] == {"width": 192, "height": 208, "columns": 8, "rows": 9}
    assert manifest["_generation"]["sourceLayout"] == "premium-action-rows-6-4-5"
    assert "enrichedDescription" not in manifest["_generation"]


def test_build_pet_assets_records_enriched_description(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    make_source().save(source_path)
    result = build_pet_assets(
        source_path,
        tmp_path / "pet",
        pet_id="pet-enriched",
        description="一只猫",
        model="test-model",
        prompt="test prompt",
        enriched_description="一只橘色的圆脸小猫，戴蓝色围巾，性格好奇又慵懒",
    )

    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
    assert manifest["description"] == "一只猫"
    assert manifest["_generation"]["enrichedDescription"] == (
        "一只橘色的圆脸小猫，戴蓝色围巾，性格好奇又慵懒"
    )


def make_source() -> Image.Image:
    width, height = 960, 600
    image = Image.new("RGBA", (width, height), (0, 255, 0, 255))
    draw = ImageDraw.Draw(image)
    row_tops = [35, 220, 405]
    colors = [(236, 66, 74, 255), (58, 118, 234, 255), (238, 158, 48, 255)]
    for row_index, count in enumerate((6, 4, 5)):
        cell_width = width / count
        top = row_tops[row_index]
        for col in range(count):
            cx = int(cell_width * (col + 0.5))
            draw.ellipse((cx - 34, top + 56, cx + 34, top + 134), fill=colors[row_index])
            draw.ellipse((cx - 24, top + 20, cx + 24, top + 62), fill=colors[row_index])
            draw.ellipse((cx - 34, top + 10, cx - 16, top + 32), fill=colors[row_index])
            draw.ellipse((cx + 16, top + 10, cx + 34, top + 32), fill=colors[row_index])
    return image


def crop_frame(sprite: Image.Image, frame_index: int, spec: SpriteSpec) -> Image.Image:
    col = frame_index % spec.columns
    row = frame_index // spec.columns
    return sprite.crop(
        (
            col * spec.frame_width,
            row * spec.frame_height,
            (col + 1) * spec.frame_width,
            (row + 1) * spec.frame_height,
        )
    )
