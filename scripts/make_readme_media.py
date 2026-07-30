"""Generate README and social media visuals from local project assets.

Run:
    QT_QPA_PLATFORM=offscreen python scripts/make_readme_media.py

Outputs:
    docs/images/readme-showcase.png
    docs/images/readme-desktop-running.png
    docs/images/readme-ui-showcase.png
    docs/images/desktop-demo.gif
    docs/social/xhs-cover.png
    docs/social/xhs-desktop-running.png
    docs/social/xhs-ui-showcase.png
    docs/social/petgen-desktop-demo.mp4
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageSequence

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "docs" / "images"
SOCIAL_DIR = ROOT / "docs" / "social"

FONT_CJK = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
FONT_BOLD = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_MEDIUM = "/System/Library/Fonts/Helvetica.ttc"

BG = (245, 247, 251)
INK = (15, 23, 42)
MUTED = (100, 116, 139)
INDIGO = (79, 70, 229)
SKY = (14, 165, 233)
ROSE = (225, 29, 72)
AMBER = (245, 158, 11)
GREEN = (16, 185, 129)


@dataclass(frozen=True)
class GeneratedPaths:
    readme_showcase: Path
    desktop_running: Path
    ui_showcase: Path
    desktop_gif: Path
    xhs_cover: Path
    xhs_desktop: Path
    xhs_ui: Path
    desktop_mp4: Path


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _draw_round(
    img: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int] | tuple[int, int, int],
    outline: tuple[int, int, int, int] | tuple[int, int, int] | None = None,
    width: int = 1,
) -> None:
    ImageDraw.Draw(img).rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _shadow_card(size: tuple[int, int], radius: int = 28, fill=(255, 255, 255, 255)) -> Image.Image:
    w, h = size
    shadow = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((30, 26, w + 30, h + 26), radius=radius, fill=(15, 23, 42, 34))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    card = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    card.alpha_composite(shadow)
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle((30, 30, w + 30, h + 30), radius=radius, fill=fill)
    cd.rounded_rectangle((30, 30, w + 30, h + 30), radius=radius, outline=(226, 232, 240, 255), width=1)
    return card


def _paste_fit(dst: Image.Image, src: Image.Image, box: tuple[int, int, int, int], *, cover: bool = False) -> None:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    im = src.convert("RGBA")
    scale = max(w / im.width, h / im.height) if cover else min(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if cover:
        left = max(0, (im.width - w) // 2)
        top = max(0, (im.height - h) // 2)
        im = im.crop((left, top, left + w, top + h))
        dst.alpha_composite(im, (x1, y1))
    else:
        dst.alpha_composite(im, (x1 + (w - im.width) // 2, y1 + (h - im.height) // 2))


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill=INK) -> None:
    draw.text(xy, text, font=font, fill=fill)


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        img.putpixel(
            (0, y),
            tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)),
        )
    return img.resize((w, h)).convert("RGBA")


def _load_idle_frames() -> list[Image.Image]:
    path = IMG_DIR / "idle.gif"
    frames = []
    with Image.open(path) as gif:
        for frame in ImageSequence.Iterator(gif):
            frames.append(frame.convert("RGBA"))
    if not frames:
        raise RuntimeError(f"no frames found in {path}")
    return frames


def _pet_on_stage(frame: Image.Image, size: tuple[int, int]) -> Image.Image:
    stage = Image.new("RGBA", size, (0, 0, 0, 0))
    w, h = size
    d = ImageDraw.Draw(stage)
    d.ellipse((w * 0.18, h * 0.78, w * 0.82, h * 0.94), fill=(15, 23, 42, 38))
    pet = frame.copy()
    pet.thumbnail((int(w * 0.82), int(h * 0.82)), Image.LANCZOS)
    stage.alpha_composite(pet, ((w - pet.width) // 2, int(h * 0.1)))
    return stage


def _desktop_frame(frame: Image.Image, index: int, size=(1280, 720)) -> Image.Image:
    canvas = _gradient(size, (235, 244, 255), (255, 246, 238))
    draw = ImageDraw.Draw(canvas)
    w, h = size

    draw.rectangle((0, 0, w, 34), fill=(255, 255, 255, 190))
    _text(draw, (24, 8), "PetGen", _font(FONT_BOLD, 16), (30, 41, 59))
    _text(draw, (1080, 8), "10:24  Thu", _font(FONT_MEDIUM, 15), (71, 85, 105))

    card = _shadow_card((760, 500), radius=22, fill=(21, 25, 43, 246))
    canvas.alpha_composite(card, (62, 86))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((112, 128, 782, 540), radius=16, fill=(15, 23, 42))
    draw.rectangle((112, 128, 782, 172), fill=(30, 41, 59))
    for i, color in enumerate(((248, 113, 113), (251, 191, 36), (52, 211, 153))):
        draw.ellipse((134 + i * 24, 144, 148 + i * 24, 158), fill=color)
    _text(draw, (134, 196), "petgen generate \\", _font(FONT_MEDIUM, 24), (226, 232, 240))
    _text(draw, (134, 236), '  --prompt "一只陪你写代码的桌面宠物"', _font(FONT_CJK, 22), (165, 180, 252))
    _text(draw, (134, 276), "petgen app", _font(FONT_MEDIUM, 24), (125, 211, 252))
    cursor = "█" if (index // 8) % 2 == 0 else " "
    _text(draw, (134, 330), f"桌宠已常驻桌面 {cursor}", _font(FONT_CJK, 24), (187, 247, 208))

    side = _shadow_card((310, 260), radius=22, fill=(255, 255, 255, 248))
    canvas.alpha_composite(side, (878, 114))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (930, 168), "AI 任务完成", _font(FONT_CJK, 28), INK)
    _text(draw, (930, 214), "宠物会切表情、弹气泡、发音效", _font(FONT_CJK, 18), MUTED)
    for y, label, color in ((268, "Codex", INDIGO), (314, "Claude Code", SKY), (360, "Antigravity", GREEN)):
        draw.rounded_rectangle((930, y, 1100, y + 28), radius=14, fill=color + (28,))
        _text(draw, (950, y + 4), label, _font(FONT_MEDIUM, 15), color)

    bubble_y = 472 + int(math.sin(index / 8) * 5)
    draw.rounded_rectangle((762, bubble_y, 1168, bubble_y + 86), radius=26, fill=(255, 255, 255, 245))
    draw.polygon(((1060, bubble_y + 82), (1106, bubble_y + 82), (1086, bubble_y + 118)), fill=(255, 255, 255, 245))
    _text(draw, (804, bubble_y + 22), "我已经在桌面陪跑啦，任务完成会提醒你。", _font(FONT_CJK, 22), INK)

    pet_scale = 260 + int(math.sin(index / 5) * 4)
    pet = _pet_on_stage(frame, (pet_scale, pet_scale))
    canvas.alpha_composite(pet, (944, 440 + int(math.sin(index / 6) * 8)))
    return canvas.convert("RGB")


def _render_qt_panels(output_dir: Path) -> tuple[Path, Path]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from PySide6.QtWidgets import QApplication

    from petgen.library_dialog import LibraryDialog
    from petgen.store import PetRecord
    from petgen.usage_panel import UsagePanelDialog
    from petgen.usage_tracker import UsageTracker

    app = QApplication.instance() or QApplication(["make-readme-media"])
    records = []
    pet_files = [
        ("pet-cat", "灰白小猫", "preset"),
        ("pet-redpanda", "熊猫团团", "preset"),
        ("pet-fox", "北极狐", "preset"),
        ("pet-gingercat", "橘猫宝宝", "custom"),
        ("pet-dragon", "奶绿龙", "custom"),
        ("pet-corgi", "柯基幼崽", "custom"),
    ]
    for pet_id, name, model in pet_files:
        preview = IMG_DIR / f"{pet_id}.png"
        records.append(
            PetRecord(
                id=pet_id if model != "custom" else f"custom-{pet_id}",
                display_name=name,
                dir_path=str(IMG_DIR),
                sprite_path=str(preview),
                manifest_path=str(IMG_DIR / "spritesheet.png"),
                preview_path=str(preview),
                model=model,
                prompt="README media render",
                description="README media render",
                created_at="2026-07-30T00:00:00Z",
                updated_at="2026-07-30T00:00:00Z",
            )
        )

    library_path = output_dir / "readme-ui-library.png"
    usage_path = output_dir / "readme-ui-usage.png"

    library = LibraryDialog()
    library.resize(960, 760)
    library.refresh(records, selected_id="pet-cat")
    library.show()
    app.processEvents()
    library.grab().save(str(library_path))
    library.close()

    tracker = UsageTracker(work_threshold_seconds=45 * 60)
    tracker.active_seconds = 32 * 60 + 18
    tracker.today_seconds = 3 * 3600 + 26 * 60
    tracker.reminders_today = 3
    usage = UsagePanelDialog(tracker)
    usage.resize(390, 340)
    usage.show()
    app.processEvents()
    usage.grab().save(str(usage_path))
    usage.close()
    return library_path, usage_path


def _make_ui_showcase(library_path: Path, usage_path: Path) -> Image.Image:
    canvas = Image.new("RGBA", (1280, 760), BG)
    draw = ImageDraw.Draw(canvas)
    _text(draw, (72, 54), "看得见的桌宠工作台", _font(FONT_CJK, 48), INK)
    _text(draw, (74, 124), "宠物中心、健康提醒、AI 工具接入都在同一个托盘应用里", _font(FONT_CJK, 25), MUTED)

    rich_library = IMG_DIR / "ui-pet-center.png"
    lib = Image.open(rich_library if rich_library.exists() else library_path).convert("RGBA")
    use = Image.open(usage_path).convert("RGBA")
    lib_card = _shadow_card((820, 570), radius=28)
    canvas.alpha_composite(lib_card, (42, 160))
    _paste_fit(canvas, lib, (92, 210, 852, 700), cover=True)

    use_card = _shadow_card((360, 332), radius=28)
    canvas.alpha_composite(use_card, (864, 306))
    _paste_fit(canvas, use, (914, 356, 1214, 618), cover=True)

    for x, y, label, color in (
        (916, 202, "切换宠物", INDIGO),
        (1050, 202, "创建新宠", ROSE),
        (916, 248, "久坐提醒", GREEN),
        (1050, 248, "AI 联动", SKY),
    ):
        draw.rounded_rectangle((x, y, x + 126, y + 36), radius=18, fill=(255, 255, 255, 245))
        draw.rounded_rectangle((x, y, x + 126, y + 36), radius=18, outline=color, width=2)
        draw.ellipse((x + 14, y + 13, x + 24, y + 23), fill=color)
        _text(draw, (x + 34, y + 8), label, _font(FONT_CJK, 17), INK)
    return canvas.convert("RGB")


def _make_showcase(desktop: Image.Image, ui: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", (1400, 840), (246, 248, 252, 255))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (78, 62), "一句话生成，真的养在桌面上", _font(FONT_CJK, 56), INK)
    _text(draw, (82, 136), "从 AI 生图、绿幕切帧到托盘常驻，桌宠会呼吸、弹气泡、回应你的 AI 编码任务。", _font(FONT_CJK, 25), MUTED)

    dcard = _shadow_card((790, 444), radius=34)
    canvas.alpha_composite(dcard, (46, 238))
    _paste_fit(canvas, desktop.convert("RGBA"), (96, 288, 826, 672), cover=True)

    ucard = _shadow_card((430, 444), radius=34)
    canvas.alpha_composite(ucard, (886, 238))
    _paste_fit(canvas, ui.convert("RGBA"), (936, 288, 1306, 672), cover=True)

    pets = ["pet-cat.png", "pet-redpanda.png", "pet-fox.png", "pet-gingercat.png", "pet-dragon.png"]
    for i, name in enumerate(pets):
        p = Image.open(IMG_DIR / name).convert("RGBA")
        p.thumbnail((98, 98), Image.LANCZOS)
        x = 114 + i * 112
        y = 724
        draw.ellipse((x - 10, y + 72, x + 100, y + 98), fill=(15, 23, 42, 26))
        canvas.alpha_composite(p, (x + (88 - p.width) // 2, y + (90 - p.height) // 2))
    return canvas.convert("RGB")


def _make_xhs_cover(desktop: Image.Image, ui: Image.Image) -> Image.Image:
    canvas = _gradient((1242, 1660), (239, 246, 255), (255, 247, 237))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (86, 104), "我把 AI 宠物", _font(FONT_CJK, 86), INK)
    _text(draw, (86, 206), "养在了桌面上", _font(FONT_CJK, 86), INK)
    _text(draw, (92, 326), "一句话生成  ·  托盘常驻  ·  编码任务会回应", _font(FONT_CJK, 34), MUTED)

    dcard = _shadow_card((1010, 568), radius=42)
    canvas.alpha_composite(dcard, (56, 486))
    _paste_fit(canvas, desktop.convert("RGBA"), (106, 536, 1056, 1004), cover=True)

    hero = Image.open(IMG_DIR / "pet-cat.png").convert("RGBA")
    hero.thumbnail((300, 300), Image.LANCZOS)
    canvas.alpha_composite(hero, (852, 296))

    chips = [("AI 生图", INDIGO), ("绿幕切帧", GREEN), ("桌面运行", SKY), ("任务提醒", ROSE)]
    x, y = 96, 1104
    for label, color in chips:
        draw.rounded_rectangle((x, y, x + 220, y + 58), radius=29, fill=(255, 255, 255, 245))
        draw.rounded_rectangle((x, y, x + 220, y + 58), radius=29, outline=color, width=3)
        draw.ellipse((x + 28, y + 23, x + 40, y + 35), fill=color)
        _text(draw, (x + 56, y + 13), label, _font(FONT_CJK, 28), INK)
        x += 248

    ucard = _shadow_card((840, 380), radius=38)
    canvas.alpha_composite(ucard, (156, 1214))
    _paste_fit(canvas, ui.convert("RGBA"), (206, 1264, 986, 1544), cover=True)
    _text(draw, (90, 1572), "github.com/ln2146/ai-desktop-pet-generator", _font(FONT_MEDIUM, 28), (71, 85, 105))
    return canvas.convert("RGB")


def _make_xhs_desktop(desktop: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", (1242, 1660), (248, 250, 252, 255))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (82, 86), "桌面运行效果", _font(FONT_CJK, 76), INK)
    _text(draw, (88, 186), "不是贴图预览，是真正能悬浮陪跑的宠物窗口", _font(FONT_CJK, 32), MUTED)
    card = _shadow_card((1050, 590), radius=44)
    canvas.alpha_composite(card, (46, 326))
    _paste_fit(canvas, desktop.convert("RGBA"), (96, 376, 1086, 866), cover=True)
    frames = _load_idle_frames()
    for i in range(4):
        pet = _pet_on_stage(frames[(i * 2) % len(frames)], (210, 210))
        x = 120 + i * 270
        y = 1030 + int(math.sin(i) * 12)
        draw.rounded_rectangle((x - 20, y - 12, x + 220, y + 250), radius=34, fill=(255, 255, 255, 235))
        canvas.alpha_composite(pet, (x, y))
    _text(draw, (90, 1440), "会呼吸、会弹气泡，也能接入 Codex / Claude Code / Antigravity。", _font(FONT_CJK, 36), INK)
    _text(draw, (90, 1504), "短视频素材：docs/social/petgen-desktop-demo.mp4", _font(FONT_CJK, 28), MUTED)
    return canvas.convert("RGB")


def _make_xhs_ui(ui: Image.Image, usage_path: Path) -> Image.Image:
    canvas = _gradient((1242, 1660), (255, 255, 255), (239, 246, 255))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (82, 86), "桌宠也有工作台", _font(FONT_CJK, 76), INK)
    _text(draw, (88, 184), "宠物中心、健康提醒、AI 工具接入，都能在托盘里打开", _font(FONT_CJK, 32), MUTED)
    rich_library = Image.open(IMG_DIR / "ui-pet-center.png").convert("RGBA")
    usage = Image.open(usage_path).convert("RGBA")

    card = _shadow_card((1040, 700), radius=44)
    canvas.alpha_composite(card, (52, 326))
    _paste_fit(canvas, rich_library, (102, 376, 1082, 966), cover=True)

    usage_card = _shadow_card((440, 386), radius=42)
    canvas.alpha_composite(usage_card, (662, 996))
    _paste_fit(canvas, usage, (712, 1046, 1092, 1332), cover=True)

    for x, y, label, color in (
        (96, 1080, "管理所有宠物", INDIGO),
        (96, 1164, "生成自定义形象", ROSE),
        (96, 1248, "统计今日使用", GREEN),
    ):
        draw.rounded_rectangle((x, y, x + 360, y + 64), radius=32, fill=(255, 255, 255, 245))
        draw.rounded_rectangle((x, y, x + 360, y + 64), radius=32, outline=color, width=3)
        draw.ellipse((x + 34, y + 25, x + 48, y + 39), fill=color)
        _text(draw, (x + 70, y + 15), label, _font(FONT_CJK, 28), INK)
    _text(draw, (90, 1510), "适合 README、帖子配图、项目介绍页直接复用。", _font(FONT_CJK, 34), INK)
    return canvas.convert("RGB")


def _write_video_and_gif(frames: list[Image.Image], paths: GeneratedPaths) -> None:
    small = [f.resize((640, 360), Image.LANCZOS) for f in frames]
    small[0].save(
        paths.desktop_gif,
        save_all=True,
        append_images=small[1:],
        duration=80,
        loop=0,
        optimize=True,
    )

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to write mp4")
    with tempfile.TemporaryDirectory() as tmp:
        frame_dir = Path(tmp)
        for i, frame in enumerate(frames):
            frame.save(frame_dir / f"frame-{i:04d}.png")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-framerate",
                "15",
                "-i",
                str(frame_dir / "frame-%04d.png"),
                "-vf",
                "scale=1280:-2",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(paths.desktop_mp4),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    paths = GeneratedPaths(
        readme_showcase=IMG_DIR / "readme-showcase.png",
        desktop_running=IMG_DIR / "readme-desktop-running.png",
        ui_showcase=IMG_DIR / "readme-ui-showcase.png",
        desktop_gif=IMG_DIR / "desktop-demo.gif",
        xhs_cover=SOCIAL_DIR / "xhs-cover.png",
        xhs_desktop=SOCIAL_DIR / "xhs-desktop-running.png",
        xhs_ui=SOCIAL_DIR / "xhs-ui-showcase.png",
        desktop_mp4=SOCIAL_DIR / "petgen-desktop-demo.mp4",
    )

    frames_src = _load_idle_frames()
    desktop_frames = [_desktop_frame(frames_src[i % len(frames_src)], i) for i in range(72)]
    desktop = desktop_frames[18]
    with tempfile.TemporaryDirectory() as tmp:
        library_path, usage_path = _render_qt_panels(Path(tmp))
        ui = _make_ui_showcase(library_path, usage_path)
        showcase = _make_showcase(desktop, ui)

        desktop.save(paths.desktop_running, optimize=True)
        ui.save(paths.ui_showcase, optimize=True)
        showcase.save(paths.readme_showcase, optimize=True)
        _make_xhs_cover(desktop, ui).save(paths.xhs_cover, optimize=True)
        _make_xhs_desktop(desktop).save(paths.xhs_desktop, optimize=True)
        _make_xhs_ui(ui, usage_path).save(paths.xhs_ui, optimize=True)
        _write_video_and_gif(desktop_frames, paths)

    for path in paths.__dict__.values():
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
