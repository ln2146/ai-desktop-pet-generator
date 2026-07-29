"""Compose the 6 showcase pets into one gallery strip for the README.

Picks the preview.png of each featured pet, drops each onto a soft studio
tile (so transparent backgrounds read cleanly), and lays them out in a single
horizontal row with a caption label under each.

Run:  python scripts/make_pet_gallery.py
Output: docs/images/gallery-showcase.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "docs" / "images"
OUT = IMG_DIR / "gallery-showcase.png"

# (source preview path, caption) — Chinese names as requested for the README
PETS = [
    ("pet-cat.png", "灰白小猫"),
    ("pet-redpanda.png", "熊猫团团"),
    ("pet-fox.png", "北极狐"),
    ("pet-gingercat.png", "橘猫宝宝"),
    ("pet-dragon.png", "奶绿龙"),
    ("pet-corgi.png", "柯基幼崽"),
]

TILE = 168          # square tile side (logical px)
PAD = 16            # outer padding
GAP = 12            # gap between tiles
CAPTION_H = 34      # caption strip height

FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

# studio backdrop colours (warm light centre -> cool edge, like the app cards)
BG_CENTER = (252, 253, 255)
BG_EDGE = (230, 234, 242)
BORDER = (225, 230, 242)
CAPTION_BG = (244, 246, 252)
TEXT = (30, 41, 59)
TEXT_MUTED = (100, 116, 139)


def _studio_tile(size: int) -> Image.Image:
    """A soft studio background tile: radial gradient warm-centre → cool-edge."""
    import math

    cx = cy = size / 2
    max_r = math.hypot(cx, cy)
    # Render a 1-D vertical gradient is too flat; build a true radial via per-pixel.
    tile = Image.new("RGB", (size, size))
    px = tile.load()
    for y in range(size):
        for x in range(size):
            t = min(1.0, math.hypot(x - cx, y - cy) / max_r)
            r = int(BG_CENTER[0] + (BG_EDGE[0] - BG_CENTER[0]) * t)
            g = int(BG_CENTER[1] + (BG_EDGE[1] - BG_CENTER[1]) * t)
            b = int(BG_CENTER[2] + (BG_EDGE[2] - BG_CENTER[2]) * t)
            px[x, y] = (r, g, b)
    return tile


def _compose(pet_path: Path, tile: Image.Image) -> Image.Image:
    """Place the pet (transparent PNG) centred on the studio tile."""
    pet = Image.open(pet_path).convert("RGBA")
    side = int(tile.width * 0.86)
    pet.thumbnail((side, side))
    x = (tile.width - pet.width) // 2
    y = (tile.height - pet.height) // 2 - 4
    out = tile.convert("RGBA")
    out.alpha_composite(pet, (x, y))
    return out.convert("RGB")


def main() -> None:
    n = len(PETS)
    img_w = PAD * 2 + n * TILE + (n - 1) * GAP
    img_h = PAD * 2 + TILE + CAPTION_H
    canvas = Image.new("RGB", (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    caption_font = ImageFont.truetype(FONT, 20) if Path(FONT).exists() else ImageFont.load_default()

    x = PAD
    y = PAD
    for src, caption in PETS:
        pet_path = IMG_DIR / src
        tile = _studio_tile(TILE)
        composed = _compose(pet_path, tile)
        canvas.paste(composed, (x, y))
        # hairline border
        draw.rounded_rectangle([x, y, x + TILE - 1, y + TILE - 1], radius=12, outline=BORDER, width=1)
        # caption
        cy = y + TILE + 8
        draw.text((x + TILE // 2, cy), caption, font=caption_font, fill=TEXT, anchor="mt")

        x += TILE + GAP

    canvas.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB)  {canvas.size}")


if __name__ == "__main__":
    main()
