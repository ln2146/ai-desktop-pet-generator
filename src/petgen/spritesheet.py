from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


class SpriteBuildError(RuntimeError):
    """Raised when the generated source sheet cannot be converted safely."""


@dataclass(frozen=True)
class SpriteSpec:
    frame_width: int = 192
    frame_height: int = 208
    columns: int = 8
    rows: int = 9
    source_row_counts: tuple[int, int, int] = (6, 4, 5)
    target_height_ratio: float = 0.82
    target_width_ratio: float = 0.88


DEFAULT_ANIMATIONS = {
    "idle": {"frames": [0, 1, 2, 3, 4, 5], "fps": 1.0, "loop": True, "fallback": "idle"},
    "happy": {"frames": [32, 33, 34, 35, 36], "fps": 4.0, "loop": False, "fallback": "idle"},
    "attentive": {"frames": [24, 25, 26, 27], "fps": 3.0, "loop": False, "fallback": "idle"},
    "busy": {"frames": [56, 57, 58, 59, 60, 61], "fps": 5.0, "loop": True, "fallback": "idle"},
    "alert": {"frames": [48, 49, 50, 51, 52, 53], "fps": 4.0, "loop": False, "fallback": "idle"},
    "error": {"frames": [40, 41, 42, 43, 44, 45, 46, 47], "fps": 4.0, "loop": False, "fallback": "idle"},
}


def build_pet_assets(
    source_image_path: Path,
    output_dir: Path,
    *,
    pet_id: str,
    display_name: str = "自定义桌宠",
    description: str = "由 AI 生成的高质感桌宠",
    model: str,
    prompt: str,
    enriched_description: str | None = None,
    spec: SpriteSpec = SpriteSpec(),
) -> dict[str, Path]:
    source = Image.open(source_image_path).convert("RGBA")
    source_rows = crop_premium_action_rows(source, spec)
    sprite = compose_sprite_sheet(source_rows, spec)

    output_dir.mkdir(parents=True, exist_ok=True)
    sprite_path = output_dir / "sprite.png"
    manifest_path = output_dir / "pet.json"
    preview_path = output_dir / "preview.png"

    sprite.save(sprite_path)
    make_preview(sprite, spec).save(preview_path)
    generation = {
        "model": model,
        "sourceImageWidth": source.width,
        "sourceImageHeight": source.height,
        "sourceLayout": "premium-action-rows-6-4-5",
        "frameLayout": f"{spec.columns}x{spec.rows}",
        "prompt": prompt,
    }
    if enriched_description and enriched_description != description:
        generation["enrichedDescription"] = enriched_description
    manifest = {
        "id": pet_id,
        "displayName": display_name,
        "description": description,
        "spritesheetPath": sprite_path.name,
        "frame": {
            "width": spec.frame_width,
            "height": spec.frame_height,
            "columns": spec.columns,
            "rows": spec.rows,
        },
        "animations": DEFAULT_ANIMATIONS,
        "_generation": generation,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sprite": sprite_path, "manifest": manifest_path, "preview": preview_path}


def crop_premium_action_rows(image: Image.Image, spec: SpriteSpec = SpriteSpec()) -> list[list[Image.Image]]:
    cutout = remove_chroma_background(image)
    row_bands = _segment_projection(
        _row_alpha_counts(cutout),
        active_threshold=max(4, cutout.width // 140),
        min_length=max(24, cutout.height // 24),
        merge_gap=max(8, cutout.height // 80),
        target_count=len(spec.source_row_counts),
    )
    if len(row_bands) != len(spec.source_row_counts):
        raise SpriteBuildError(
            f"expected {len(spec.source_row_counts)} source rows, detected {len(row_bands)}"
        )

    rows: list[list[Image.Image]] = []
    for band, expected_count in zip(row_bands, spec.source_row_counts):
        rows.append(_crop_row_frames(cutout, band, expected_count))
    return rows


def compose_sprite_sheet(source_rows: list[list[Image.Image]], spec: SpriteSpec = SpriteSpec()) -> Image.Image:
    if len(source_rows) != len(spec.source_row_counts):
        raise SpriteBuildError(f"expected {len(spec.source_row_counts)} rows, got {len(source_rows)}")
    for row, expected_count in zip(source_rows, spec.source_row_counts):
        if len(row) != expected_count:
            raise SpriteBuildError(f"expected row with {expected_count} frames, got {len(row)}")

    sprite = Image.new("RGBA", (spec.frame_width * spec.columns, spec.frame_height * spec.rows), (0, 0, 0, 0))
    output_rows = [
        (0, 1.00, 0.0),
        (0, 0.99, 0.3),
        (1, 1.00, 0.0),
        (1, 1.01, 0.0),
        (2, 1.02, 0.0),
        (1, 0.99, 1.2),
        (1, 1.01, 0.6),
        (1, 1.02, 1.5),
        (2, 1.03, 0.8),
    ]

    for out_row, (src_row, base_scale, rotation) in enumerate(output_rows):
        frames = source_rows[src_row]
        for col in range(spec.columns):
            normalized = normalize_to_frame(frames[col % len(frames)], spec)
            angle = 0.0
            if rotation:
                phase = (col % 4) - 1.5
                angle = rotation * (phase / 1.5)
            frame = _transform_frame(normalized, base_scale, angle, spec)
            x = col * spec.frame_width
            y = out_row * spec.frame_height
            sprite.alpha_composite(frame, (x, y))

    return sprite


def remove_chroma_background(image: Image.Image, *, key: tuple[int, int, int] = (0, 255, 0)) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    transparent_distance = 78.0
    soft_distance = 150.0
    span = soft_distance - transparent_distance

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            distance = math.sqrt((r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2)
            green_dominant = g > 120 and g > r * 1.25 and g > b * 1.25
            if distance <= transparent_distance or green_dominant and distance < soft_distance:
                pixels[x, y] = (0, 0, 0, 0)
            elif distance < soft_distance and green_dominant:
                new_alpha = int((distance - transparent_distance) / span * 255)
                pixels[x, y] = (min(r, max(r, b)), min(g, max(r, b)), b, max(0, min(255, new_alpha)))
    return rgba


def normalize_to_frame(image: Image.Image, spec: SpriteSpec = SpriteSpec()) -> Image.Image:
    bbox = image.getbbox()
    if bbox is None:
        raise SpriteBuildError("source frame has no visible pixels")
    cropped = image.crop(bbox)
    max_width = spec.frame_width * spec.target_width_ratio
    max_height = spec.frame_height * spec.target_height_ratio
    scale = min(max_width / cropped.width, max_height / cropped.height)
    new_size = (max(1, int(cropped.width * scale)), max(1, int(cropped.height * scale)))
    return cropped.resize(new_size, Image.Resampling.LANCZOS)


def make_preview(sprite: Image.Image, spec: SpriteSpec = SpriteSpec()) -> Image.Image:
    first = sprite.crop((0, 0, spec.frame_width, spec.frame_height))
    bbox = first.getbbox()
    if bbox is None:
        return first
    padded = (
        max(0, bbox[0] - 8),
        max(0, bbox[1] - 8),
        min(first.width, bbox[2] + 8),
        min(first.height, bbox[3] + 8),
    )
    return first.crop(padded)


def _crop_row_frames(image: Image.Image, row_band: tuple[int, int], expected_count: int) -> list[Image.Image]:
    projection = _column_alpha_counts(image, row_band)
    detected = _segment_projection(
        projection,
        active_threshold=max(4, (row_band[1] - row_band[0]) // 60),
        min_length=max(18, image.width // 80),
        merge_gap=max(8, image.width // 120),
        target_count=expected_count,
    )
    if len(detected) == expected_count:
        x_bands = detected
    else:
        cell_width = image.width / expected_count
        x_bands = [
            (int(col * cell_width), int((col + 1) * cell_width) - 1)
            for col in range(expected_count)
        ]

    frames = []
    for x_band in x_bands:
        crop = _crop_visible_content(image, x_band, row_band)
        if crop.getbbox() is None:
            raise SpriteBuildError("detected an empty frame in source sheet")
        frames.append(crop)
    return frames


def _crop_visible_content(
    image: Image.Image,
    x_band: tuple[int, int],
    y_band: tuple[int, int],
) -> Image.Image:
    alpha = image.getchannel("A")
    crop_box = (
        max(0, x_band[0]),
        max(0, y_band[0]),
        min(image.width, x_band[1] + 1),
        min(image.height, y_band[1] + 1),
    )
    local_alpha = alpha.crop(crop_box)
    bbox = local_alpha.getbbox()
    if bbox is None:
        raise SpriteBuildError("source frame has no visible pixels")
    margin = max(6, int(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.08))
    left = max(0, crop_box[0] + bbox[0] - margin)
    top = max(0, crop_box[1] + bbox[1] - margin)
    right = min(image.width, crop_box[0] + bbox[2] + margin)
    bottom = min(image.height, crop_box[1] + bbox[3] + margin)
    return image.crop((left, top, right, bottom))


def _transform_frame(image: Image.Image, scale: float, rotation: float, spec: SpriteSpec) -> Image.Image:
    scaled = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    if rotation:
        scaled = scaled.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)

    frame = Image.new("RGBA", (spec.frame_width, spec.frame_height), (0, 0, 0, 0))
    x = (spec.frame_width - scaled.width) // 2
    y = spec.frame_height - scaled.height - 14
    frame.alpha_composite(scaled, (x, y))
    return frame


def _row_alpha_counts(image: Image.Image) -> list[int]:
    alpha_bytes = image.getchannel("A").tobytes()
    counts: list[int] = []
    for y in range(image.height):
        start = y * image.width
        row = alpha_bytes[start : start + image.width]
        counts.append(sum(1 for value in row if value > 10))
    return counts


def _column_alpha_counts(image: Image.Image, row_band: tuple[int, int]) -> list[int]:
    alpha_bytes = image.getchannel("A").tobytes()
    top, bottom = row_band
    counts: list[int] = []
    for x in range(image.width):
        count = 0
        for y in range(top, bottom + 1):
            if alpha_bytes[y * image.width + x] > 10:
                count += 1
        counts.append(count)
    return counts


def _segment_projection(
    projection: list[int],
    *,
    active_threshold: int,
    min_length: int,
    merge_gap: int,
    target_count: int,
) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for index, count in enumerate(projection):
        if count >= active_threshold:
            if start is None:
                start = index
        elif start is not None:
            bands.append((start, max(start, index - 1)))
            start = None
    if start is not None:
        bands.append((start, len(projection) - 1))

    bands = [band for band in bands if band[1] - band[0] + 1 >= min_length]
    if not bands:
        return []

    merged: list[tuple[int, int]] = []
    for band in bands:
        if merged and band[0] - merged[-1][1] - 1 <= merge_gap:
            merged[-1] = (merged[-1][0], band[1])
        else:
            merged.append(band)

    while len(merged) > target_count:
        pair_index = min(
            range(len(merged) - 1),
            key=lambda i: merged[i + 1][0] - merged[i][1],
        )
        merged[pair_index] = (merged[pair_index][0], merged[pair_index + 1][1])
        merged.pop(pair_index + 1)

    return merged if len(merged) == target_count else []
