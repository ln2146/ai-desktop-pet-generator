"""Generate a 1280x640 GitHub social preview card from existing assets.

GitHub recommends 1280x640 (2:1) for the social preview image shown on
Twitter / HN / LinkedIn / GitHub cards. This composites the hero pet, a
bilingual title, and feature highlights onto a branded background.

Run:  python scripts/make_social_preview.py
Output: docs/images/social-preview.png
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "docs" / "images"
OUT = IMG_DIR / "social-preview.png"

W, H = 1280, 640

# Brand palette
BG_TOP = (45, 27, 78)          # deep purple
BG_BOTTOM = (24, 20, 44)       # near-black purple
ACCENT = (255, 180, 120)       # warm amber
ACCENT_SOFT = (255, 210, 170)
TEXTPrimary = (255, 255, 255)
TEXT_MUTED = (200, 195, 220)
CARD_BG = (255, 255, 255, 18)  # translucent white for chips

FONT_BOLD = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_MEDIUM = "/System/Library/Fonts/Helvetica.ttc"
FONT_CJK = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        base.putpixel((0, y), (r, g, b))
    return base.resize((w, h))


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _paste_rounded_card(canvas: Image.Image, xy: tuple[int, int], wh: tuple[int, int],
                        radius: int, fill) -> None:
    card = Image.new("RGBA", wh, (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, wh[0] - 1, wh[1] - 1], radius=radius, fill=fill)
    canvas.alpha_composite(card, xy)


def main() -> None:
    canvas = Image.new("RGBA", (W, H), BG_BOTTOM)
    grad = _vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    canvas.alpha_composite(grad)

    # Subtle accent glow in the top-right
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 360, -260, W + 120, 220], fill=(255, 180, 120, 45))
    canvas.alpha_composite(glow)

    draw = ImageDraw.Draw(canvas)

    # --- Title block (left) ---
    margin = 72
    eyebrow_font = _font(FONT_BOLD, 30)
    title_font_en = _font(FONT_BOLD, 68)
    title_font_cn = _font(FONT_CJK, 38)
    sub_font = _font(FONT_MEDIUM, 22)

    # Eyebrow
    eyebrow = "🐾  AI · DESKTOP PET"
    draw.text((margin, 96), eyebrow, font=eyebrow_font, fill=ACCENT)

    # English title
    draw.text((margin, 150), "Turn a sentence", font=title_font_en, fill=TEXTPrimary)
    draw.text((margin, 224), "into a desktop pet.", font=title_font_en, fill=TEXTPrimary)

    # Chinese subtitle
    cn = "一句话生成一只常驻桌面的高质感宠物"
    draw.text((margin, 312), cn, font=title_font_cn, fill=ACCENT_SOFT)

    # Pipeline tagline
    pipe = "AI image  →  green-screen keying  →  8×9 spritesheet  →  tray-resident pet"
    draw.text((margin, 372), pipe, font=sub_font, fill=TEXT_MUTED)

    # --- Feature chips ---
    chips = ["文字 / 参考图生宠", "本地后处理", "托盘常驻 App", "AI 编码联动", "语音 · 提醒 · 番茄钟"]
    chip_font = _font(FONT_CJK, 19)
    cx, cy = margin, 430
    gap = 12
    for label in chips:
        tw = _text_w(draw, label, chip_font)
        chip_w = tw + 28
        _paste_rounded_card(canvas, (cx, cy), (chip_w, 40), radius=20, fill=CARD_BG)
        # accent dot
        dot = Image.new("RGBA", (10, 40), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dot)
        dd.ellipse([0, 15, 8, 23], fill=ACCENT + (255,))
        canvas.alpha_composite(dot, (cx + 14, cy))
        draw.text((cx + 30, cy + 9), label, font=chip_font, fill=TEXTPrimary)
        cx += chip_w + gap

    # --- Hero image (right) ---
    hero_path = IMG_DIR / "hero.png"
    if hero_path.exists():
        hero = Image.open(hero_path).convert("RGBA")
        # Soft circle backdrop behind hero
        hw = 360
        hx, hy = W - hw - 110, 150
        backdrop = Image.new("RGBA", (hw, hw), (0, 0, 0, 0))
        bd = ImageDraw.Draw(backdrop)
        bd.ellipse([0, 0, hw - 1, hw - 1], fill=(255, 255, 255, 22))
        canvas.alpha_composite(backdrop, (hx, hy))

        # Fit hero inside the circle, centered
        hero.thumbnail((300, 300))
        # Draw on a checkerboard-free transparent paste
        canvas.alpha_composite(hero, (hx + (hw - hero.width) // 2, hy + (hw - hero.height) // 2))

        # Idle gif note
        note_font = _font(FONT_MEDIUM, 16)
        draw.text((hx + 40, hy + hw + 14), "breathing idle animation",
                  font=note_font, fill=TEXT_MUTED)

    # --- Footer ---
    foot_font = _font(FONT_MEDIUM, 20)
    repo = "github.com/ln2146/ai-desktop-pet-generator"
    draw.text((margin, H - 56), repo, font=foot_font, fill=TEXT_MUTED)

    # Badges row (right footer)
    badge_font = _font(FONT_BOLD, 18)
    badges = [("MIT", (120, 200, 120)), ("Python ≥3.10", (90, 150, 240)), ("pytest · ruff", (255, 180, 120))]
    bx = W - margin
    by = H - 56
    for label, color in reversed(badges):
        tw = _text_w(draw, label, badge_font) + 22
        bx -= tw + 10
        _paste_rounded_card(canvas, (bx, by), (tw, 32), radius=16,
                            fill=color + (35,))
        # left bar
        bar = Image.new("RGBA", (4, 32), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(bar)
        bdraw.rectangle([0, 0, 4, 32], fill=color + (255,))
        canvas.alpha_composite(bar, (bx, by))
        draw.text((bx + 12, by + 6), label, font=badge_font, fill=TEXTPrimary)

    canvas.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
