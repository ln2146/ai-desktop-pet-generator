"""Generate app icons (macOS .icns + Windows .ico) from the grey-white cat.

Builds a high-res square source (cat on a brand-gradient rounded tile), then
fans it out into the full iconset sizes for iconutil (.icns) and the Windows
multi-size .ico.

Run:  python packaging/make_app_icon.py
Outputs:
  packaging/PetGen.icns  (macOS — uses iconutil, macOS-only)
  packaging/PetGen.ico   (Windows — Pillow, cross-platform)
  docs/images/app-icon.png  (README/GitHub preview)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PET = ROOT / "docs/images/pet-cat.png"
ICONSET = ROOT / "packaging/PetGen.iconset"
OUT_ICNS = ROOT / "packaging/PetGen.icns"
OUT_ICO = ROOT / "packaging/PetGen.ico"
OUT_PNG = ROOT / "docs/images/app-icon.png"

# macOS iconset: (logical px, scale). 1024 covers the largest @2x bucket.
MAC_SIZES = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (64, 1), (64, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
    (1024, 1), (1024, 2),
]

# Windows .ico embeds multiple sizes in one file.
WIN_SIZES = [16, 24, 32, 48, 64, 128, 256]

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

    # the cat, cropped tight to its body and scaled to FILL the tile (~95%).
    # First trim the transparent padding so we don't upscale empty space, then
    # fit the pet to nearly the full squircle, leaving a small margin so the
    # rounded corners don't clip ears/feet.
    cat = Image.open(PET).convert("RGBA")
    bbox = cat.split()[-1].getbbox()
    if bbox:
        cat = cat.crop(bbox)
    fill = int(size * 0.95)
    scale = min(fill / cat.width, fill / cat.height)
    cat = cat.resize((max(1, int(cat.width * scale)), max(1, int(cat.height * scale))), Image.LANCZOS)
    cx = (size - cat.width) // 2
    cy = (size - cat.height) // 2
    canvas.alpha_composite(cat, (cx, cy))

    return canvas


def build_icns(source: Image.Image) -> None:
    """Build .icns via iconutil (macOS only). Skipped on other platforms."""
    if sys.platform != "darwin":
        print("skip .icns (not macOS)")
        return
    ICONSET.mkdir(exist_ok=True)
    for f in ICONSET.iterdir():
        f.unlink()
    for logical, scale in MAC_SIZES:
        px = logical * scale
        source.resize((px, px), Image.LANCZOS).save(
            ICONSET / f"icon_{logical}x{logical}{'@2x' if scale == 2 else ''}.png"
        )
    if OUT_ICNS.exists():
        OUT_ICNS.unlink()
    r = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(OUT_ICNS)],
        capture_output=True, text=True,
    )
    for f in ICONSET.iterdir():
        f.unlink()
    ICONSET.rmdir()
    if r.returncode != 0:
        print("iconutil failed:", r.stderr)
        raise SystemExit(1)
    print(f"wrote {OUT_ICNS} ({OUT_ICNS.stat().st_size // 1024} KB)")


def build_ico(source: Image.Image) -> None:
    """Build a multi-size Windows .ico with Pillow (cross-platform)."""
    if OUT_ICO.exists():
        OUT_ICO.unlink()
    # Pillow's ICO plugin auto-generates each requested size from the source
    # when `sizes` is passed; pass the largest frame and let it downscale.
    big = source.resize((256, 256), Image.LANCZOS)
    big.save(OUT_ICO, format="ICO", sizes=[(s, s) for s in WIN_SIZES])
    print(f"wrote {OUT_ICO} ({OUT_ICO.stat().st_size // 1024} KB)")


def build_png(source: Image.Image) -> None:
    """Build a plain PNG copy for README/GitHub rendering."""
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    source.resize((256, 256), Image.LANCZOS).save(OUT_PNG, optimize=True)
    print(f"wrote {OUT_PNG} ({OUT_PNG.stat().st_size // 1024} KB)")


def main() -> None:
    source = make_source(1024)
    build_icns(source)
    build_ico(source)
    build_png(source)


if __name__ == "__main__":
    main()
