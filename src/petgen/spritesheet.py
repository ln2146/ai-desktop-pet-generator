from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import numpy as np


class SpriteBuildError(RuntimeError):
    """Raised when the generated source sheet cannot be converted safely."""


# Chroma-key distance thresholds (Euclidean distance in RGB space to the key).
_CHROMA_TRANSPARENT_DISTANCE = 78.0  # within this: unconditionally background
_CHROMA_SOFT_DISTANCE = 150.0  # green-dominant pixels below this may be keyed


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
    )
    if len(row_bands) != len(spec.source_row_counts):
        # Safety net: the column-friendly segmentation change below makes
        # _segment_projection return its merged bands even on a count
        # mismatch; row segmentation still needs an exact count, so retry
        # with the conservative pre-fix parameters if that ever happens.
        row_bands = _segment_projection_legacy(
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
    """Remove the chroma-key background (vectorised with numpy).

    Rule, per pixel with alpha > 0:

    * very close to the key colour (``distance <= TRANSPARENT``) -> transparent;
    * green-dominant and inside the soft band -> a soft alpha ramp (anti-alias),
      so subject edges that fade into the green are feathered instead of hard
      cut, and green spill fringes are attenuated;
    * everything else (the subject body) -> left opaque.

    The previous code expressed the same intent but the soft-edge branch was
    *unreachable*: ``a or b and c`` parses as ``a or (b and c)``, so the
    green-dominant clause in the hard-cut test swallowed the ``elif`` that was
    meant to feather it. The explicit three-way branch below restores it. The
    per-pixel distance loop is now a single numpy pass (the old pure-Python
    double loop was the ~1s hotspot on a 1536x1024 sheet).

    Limitation (inherent to colour keying, not a bug): a subject whose body is
    itself green-dominant and within the soft band cannot be separated from a
    same-colour green screen by colour alone -- the two are indistinguishable.
    :func:`_despill_light_subject_edges` rescues the *edges* of green subjects
    that have a non-green core, and the prompt steers the model away from
    green-dominant bodies; a fully green pet on green remains unkeyable without
    a reference mask / learned matting.
    """
    rgba = image.convert("RGBA")
    arr = np.asarray(rgba)
    rgb = arr[..., :3].astype(np.float32)  # float32: squared sums exceed int16 range
    alpha = arr[..., 3]

    key_arr = np.asarray(key, dtype=np.float32)
    distance = np.sqrt(np.sum((rgb - key_arr) ** 2, axis=-1))
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    green_dominant = (g > 120) & (g > r * 1.25) & (g > b * 1.25)
    opaque = alpha > 0

    hard = opaque & (distance <= _CHROMA_TRANSPARENT_DISTANCE)
    soft = (
        opaque
        & ~hard
        & green_dominant
        & (distance < _CHROMA_SOFT_DISTANCE)
    )

    new_alpha = alpha.copy()
    new_alpha[hard] = 0
    span = max(1.0, _CHROMA_SOFT_DISTANCE - _CHROMA_TRANSPARENT_DISTANCE)
    ramp = (distance[soft] - _CHROMA_TRANSPARENT_DISTANCE) / span * 255.0
    new_alpha[soft] = np.clip(ramp, 0, 255).astype(np.uint8)

    out = np.empty((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
    out[..., :3] = rgb.astype(np.uint8)
    out[..., 3] = new_alpha
    rgba = Image.fromarray(out, "RGBA").copy()  # .copy() -> writable pixel buffer
    _despill_light_subject_edges(rgba)
    return rgba


def _despill_light_subject_edges(rgba: Image.Image) -> None:
    """去除近白/浅色主体轮廓上的绿幕混色光晕（原地修改）。

    仅处理紧邻透明像素的轮廓环；且仅当环像素"朝内的本体颜色非绿主导"时才压绿，
    以免误伤奶绿龙/树蛙等绿色角色的本体边缘。详见记忆 white-subject-green-halo。
    """
    from PIL import ImageChops, ImageFilter

    alpha = rgba.getchannel("A")
    transp = alpha.point(lambda v: 255 if v == 0 else 0)
    near = transp.filter(ImageFilter.MaxFilter(7))  # 距透明 <=3px 的区域
    opaque = alpha.point(lambda v: 255 if v > 0 else 0)
    ring = ImageChops.multiply(near, opaque)
    rb = ring.getbbox()
    if not rb:
        return
    px = rgba.load()
    rng = ring.load()
    width, height = rgba.size
    sample_r = 6  # 朝内采样半径，需大于环宽

    for y in range(rb[1], rb[3]):
        for x in range(rb[0], rb[2]):
            if rng[x, y] != 255:
                continue
            r, g, b, a = px[x, y]
            if a == 0 or g <= max(r, b) + 6:
                continue  # 非绿溢色像素
            ir = ig = ib = n = 0
            for dx, dy in ((sample_r, 0), (-sample_r, 0), (0, sample_r), (0, -sample_r)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < width and 0 <= yy < height:
                    pr, pg, pb, pa = px[xx, yy]
                    if pa > 0:
                        ir += pr
                        ig += pg
                        ib += pb
                        n += 1
            if n == 0:
                continue
            ir //= n
            ig //= n
            ib //= n
            if ig > ir + 15 and ig > ib + 15:
                continue  # 本体为绿色角色，保留其边缘
            ng = max(r, b) + 4
            if g <= ng:
                continue
            na = a
            d = math.sqrt(r * r + (g - 255) * (g - 255) + b * b)
            if d < 175:  # 极接近背景者轻微羽化
                na = max(0, min(a, int((d - 110) / 65 * 255)))
            px[x, y] = (r, ng, b, na)


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
    # Prefer 2D connected components: they ignore 1-3px star/spark noise (filtered
    # by area) and keep near-touching poses separate, which the old 1D column
    # projection + large merge_gap could not (it fused thin real gaps and then
    # fell back to a misaligned equal-grid, leaking neighbour limbs into frames).
    labels, info = _label_row_components(image, row_band)
    row_height = max(1, row_band[1] - row_band[0] + 1)
    min_area = max(40, row_height * 4)
    comps = [
        (info[label][0], info[label][1], label)
        for label in range(1, len(info) + 1)
        if info[label][2] >= min_area
    ]
    comps.sort(key=lambda band: band[0])

    if len(comps) == expected_count:
        x_bands = comps
    elif 1 <= len(comps) < expected_count:
        x_bands = _split_wide_bands(image, row_band, comps, expected_count)
    else:
        x_bands = []
    if len(x_bands) != expected_count:
        projection = _column_alpha_counts(image, row_band)
        detected = _segment_projection_legacy(
            projection,
            active_threshold=max(4, (row_band[1] - row_band[0]) // 60),
            min_length=max(18, image.width // 80),
            merge_gap=max(8, image.width // 120),
            target_count=expected_count,
        )
        x_bands = [(l, r, None) for l, r in detected] if len(detected) == expected_count else []
    if len(x_bands) != expected_count:
        left, right = _visible_x_extent(image, row_band)
        if left is None:
            raise SpriteBuildError("detected an empty frame in source sheet")
        x_bands = [(l, r, None) for l, r in _centered_period_bands(left, right, expected_count)]

    frames = []
    for x_band in x_bands:
        label = x_band[2]  # x_bands entries are always (left, right, label) triples
        if label:
            crop = _mask_component(image, row_band, x_band, label, labels)
        else:
            crop = _crop_visible_content(image, x_band, row_band)
        if crop.getbbox() is None:
            raise SpriteBuildError("detected an empty frame in source sheet")
        frames.append(crop)
    return frames


def _label_row_components(
    image: Image.Image, row_band: tuple[int, int]
) -> tuple[list[int], dict[int, list[int]]]:
    """8-connected component labels for a row band plus per-label ``[minx, maxx, area]``."""
    top, bottom = row_band
    width = image.width
    height = bottom + 1
    alpha = image.getchannel("A").tobytes()

    labels = [0] * (width * height)
    next_label = 0
    info: dict[int, list[int]] = {}
    stack: list[tuple[int, int]] = []
    for y in range(top, height):
        base = y * width
        for x in range(width):
            idx = base + x
            if alpha[idx] <= 10 or labels[idx]:
                continue
            next_label += 1
            labels[idx] = next_label
            minx = maxx = x
            miny = maxy = y
            area = 1
            stack.append((x, y))
            while stack:
                cx, cy = stack.pop()
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy
                for nx in (cx - 1, cx, cx + 1):
                    if nx < 0 or nx >= width:
                        continue
                    for ny in (cy - 1, cy, cy + 1):
                        if ny < top or ny >= height:
                            continue
                        nidx = ny * width + nx
                        if not labels[nidx] and alpha[nidx] > 10:
                            labels[nidx] = next_label
                            area += 1
                            stack.append((nx, ny))
            info[next_label] = [minx, maxx, area]
    return labels, info


def _split_wide_bands(
    image: Image.Image,
    row_band: tuple[int, int],
    bands: list[tuple[int, int, int]],
    expected_count: int,
) -> list[tuple[int, int, int]]:
    """Split blobs that fused neighbouring poses (touching wings / tails).

    Poses that touch at a thin limb form one over-wide blob; we recover the real
    boundary by cutting at the column-projection valley (lowest opaque density),
    which sits at the thin bridge between the two bodies.
    """
    widths = sorted(b[1] - b[0] + 1 for b in bands)
    typical = widths[len(widths) // 2]
    pieces: list[tuple[int, int, int]] = []
    for index, band in enumerate(bands):
        width = band[1] - band[0] + 1
        n = max(1, round(width / typical)) if typical > 0 else 1
        remaining = len(bands) - index - 1
        if len(pieces) + n + remaining > expected_count:
            n = max(1, expected_count - len(pieces) - remaining)
        if n > 1:
            pieces.extend(_valley_split(image, row_band, band, n))
        else:
            pieces.append(band)
    if len(pieces) != expected_count:
        return _equal_split_bands(bands, expected_count)
    return pieces


def _valley_split(
    image: Image.Image,
    row_band: tuple[int, int],
    band: tuple[int, int, int],
    pieces: int,
) -> list[tuple[int, int, int]]:
    if pieces <= 1:
        return [band]
    left, right, label = band
    width = right - left + 1
    cols = _column_alpha_counts(image, row_band)
    density = [float(cols[left + offset]) for offset in range(width)]
    span = max(1, width // (pieces * 4))

    def deepest(lo: int, hi: int) -> int:
        best = lo
        best_value = density[lo]
        for index in range(lo, hi + 1):
            if density[index] < best_value:
                best_value = density[index]
                best = index
        return best

    cuts: list[int] = []

    def recurse(lo: int, hi: int, need: int) -> None:
        if need <= 1:
            return
        if hi - lo < 2:
            step = max(1, (hi - lo) // need)
            for k in range(1, need):
                cuts.append(lo + k * step)
            return
        mid = deepest(lo + span, hi - span)
        cuts.append(left + mid)
        recurse(lo, mid, need // 2)
        recurse(mid + 1, hi, need - need // 2)

    recurse(0, width - 1, pieces)
    cuts = sorted(set(cuts))
    bounds = [left, *cuts, right + 1]
    return [(bounds[i], bounds[i + 1] - 1, label) for i in range(len(bounds) - 1)]


def _equal_split_bands(
    bands: list[tuple[int, int, int]], expected_count: int
) -> list[tuple[int, int, int]]:
    if not bands:
        return []
    left = min(b[0] for b in bands)
    right = max(b[1] for b in bands)
    return [(l, r, None) for l, r in _centered_period_bands(left, right, expected_count)]


def _visible_x_extent(
    image: Image.Image, row_band: tuple[int, int]
) -> tuple[int | None, int | None]:
    cols = _column_alpha_counts(image, row_band)
    xs = [x for x, count in enumerate(cols) if count > 0]
    if not xs:
        return None, None
    return xs[0], xs[-1]


def _centered_period_bands(left: int, right: int, count: int) -> list[tuple[int, int]]:
    period = (right - left + 1) / count
    return [
        (int(round(left + col * period)), int(round(left + (col + 1) * period)) - 1)
        for col in range(count)
    ]


def _mask_component(
    image: Image.Image,
    row_band: tuple[int, int],
    x_band: tuple[int, int, int],
    label: int,
    labels: list[int],
) -> Image.Image:
    """Crop the component ``label`` keeping only its own pixels.

    Other blobs that poke into the crop box (touching wings / tails) are zeroed by
    looking up the precomputed full-row ``labels`` array, so no neighbour residue
    survives. The crop is tightened to the component's exact visible extent.
    """
    top, _ = row_band
    left = max(0, x_band[0])
    right = min(image.width, x_band[1] + 1)
    minx = maxx = miny = maxy = None
    width = image.width
    for y in range(row_band[0], row_band[1] + 1):
        base = y * width
        for x in range(left, right):
            if labels[base + x] == label:
                if minx is None or x < minx:
                    minx = x
                if maxx is None or x > maxx:
                    maxx = x
                if miny is None or y < miny:
                    miny = y
                if maxy is None or y > maxy:
                    maxy = y
    if minx is None:
        return image.crop((left, top, right, row_band[1] + 1))
    crop = image.crop((minx, miny, maxx + 1, maxy + 1)).copy()
    pixels = crop.load()
    w, h = crop.size
    for yy in range(h):
        src_row = (miny + yy) * width
        for xx in range(w):
            if labels[src_row + minx + xx] != label:
                pixels[xx, yy] = (0, 0, 0, 0)
    return crop


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
    """Per-row count of pixels with alpha > 10 (vectorised; exact)."""
    alpha = np.asarray(image.getchannel("A"))
    return (alpha > 10).sum(axis=1).astype(int).tolist()


def _column_alpha_counts(image: Image.Image, row_band: tuple[int, int]) -> list[int]:
    """Per-column count of alpha > 10 within ``row_band`` (vectorised; exact)."""
    top, bottom = row_band
    alpha = np.asarray(image.getchannel("A"))[top : bottom + 1]
    return (alpha > 10).sum(axis=0).astype(int).tolist()


def _segment_projection(
    projection: list[int],
    *,
    active_threshold: int,
    min_length: int,
    merge_gap: int,
) -> list[tuple[int, int]]:
    """Segment a 1D projection into bands, returning the merged result.

    Unlike :func:`_segment_projection_legacy`, this returns the merged bands even
    when their count differs from the expected frame count. Column segmentation
    uses this so that a count mismatch can be recovered by connected-component
    valley splitting instead of silently collapsing to ``[]``.
    """
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

    return merged


def _segment_projection_legacy(
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
