"""Generate a macOS .icns app icon from the grey-white cat.

Builds a high-res square source (cat on a brand-gradient rounded tile), then
fans it out into the full iconset sizes required by iconutil and packs them
into an .icns.

Run:  python packaging/make_app_icon.py
Output: packaging/PetGen.icns
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PET = ROOT / "docs/images/pet-cat.png"
ICONSET = ROOT / "packaging/PetGen.iconset"
OUT_ICNS = ROOT / "packaging/PetGen.icns"

# macOS iconset: (logical px, scale). 1024 covers the largest @2x bucket.
SIZES = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (64, 1), (64, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
    (1024, 1), (1024, 2),
]

# Brand gradient matching the app (deep purple -> near-black, amber accent)
BG_TOP = (45, 27, 78)
BG_BOTTOM = (24, 18, 44)


def make_source(size: int = 1024) -> Image.Image:
    """A square source icon: rounded purple tile + the cat centred."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # vertical gradient rounded tile (vectorised for speed)
    import numpy as np

    t = np.linspace(0, 1, size).reshape(-1, 1)
    r = (BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t).astype(np.uint8)
    g = (BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t).astype(np.uint8)
    b = (BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t).astype(np.uint8)
    r = np.broadcast_to(r, (size, size))
    g = np.broadcast_to(g, (size, size))
    b = np.broadcast_to(b, (size, size))
    a = np.full((size, size), 255, dtype=np.uint8)
    grad = Image.fromarray(np.stack([r, g, b, a], axis=-1), "RGBA")

    # round corners (macOS Big Sur squircle-ish: ~22% radius)
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    canvas.paste(grad, (0, 0), mask)

    # soft amber glow behind the cat
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([size * 0.1, -size * 0.15, size * 1.05, size * 0.7], fill=(255, 180, 120, 55))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.06))
    canvas.alpha_composite(glow)

    # the cat, centred, filling ~72% of the tile
    cat = Image.open(PET).convert("RGBA")
    side = int(size * 0.72)
    cat.thumbnail((side, side))
    cx = (size - cat.width) // 2
    cy = (size - cat.height) // 2
    canvas.alpha_composite(cat, (cx, cy))

    return canvas


def main() -> None:
    ICONSET.mkdir(exist_ok=True)
    # clear stale entries
    for f in ICONSET.iterdir():
        f.unlink()

    source = make_source(1024)
    for logical, scale in SIZES:
        px = logical * scale
        img = source.resize((px, px), Image.LANCZOS)
        name = f"icon_{logical}x{logical}"
        if scale == 2:
            name += "@2x"
        img.save(ICONSET / f"{name}.png")

    # pack into .icns
    if OUT_ICNS.exists():
        OUT_ICNS.unlink()
    r = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(OUT_ICNS)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("iconutil failed:", r.stderr)
        raise SystemExit(1)

    # clean up the iconset dir
    for f in ICONSET.iterdir():
        f.unlink()
    ICONSET.rmdir()

    print(f"wrote {OUT_ICNS} ({OUT_ICNS.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
