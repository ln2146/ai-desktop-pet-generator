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
GPT_SCENE = IMG_DIR / "gpt-desktop-scene.png"
NOTIFICATION_SHOT = IMG_DIR / "readme-notification.png"
REST_REMINDER_SHOT = IMG_DIR / "readme-rest-reminder.png"
PET_CENTER_SHOT = IMG_DIR / "readme-pet-center.png"
REMINDERS_SHOT = IMG_DIR / "readme-reminders.png"
POMODORO_SHOT = IMG_DIR / "readme-pomodoro.png"
USAGE_SHOT = IMG_DIR / "readme-usage.png"

FONT_CJK = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
FONT_BOLD = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_MEDIUM = "/System/Library/Fonts/Helvetica.ttc"

BG = (245, 247, 251)
PANEL = (255, 255, 255)
INK = (15, 23, 42)
MUTED = (100, 116, 139)
FAINT = (226, 232, 240)
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


def _paste_fit_anchor(
    dst: Image.Image,
    src: Image.Image,
    box: tuple[int, int, int, int],
    *,
    anchor: tuple[float, float] = (0.5, 0.5),
) -> None:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    im = src.convert("RGBA")
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    max_left = max(0, im.width - w)
    max_top = max(0, im.height - h)
    left = int(max_left * anchor[0])
    top = int(max_top * anchor[1])
    dst.alpha_composite(im.crop((left, top, left + w, top + h)), (x1, y1))


def _required_image(path: Path) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(f"required README media source is missing: {path}")
    return Image.open(path).convert("RGBA")


def _draw_image_panel(
    dst: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    radius: int = 28,
    cover: bool = False,
    fill: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> None:
    x1, y1, x2, y2 = box
    card = _shadow_card((x2 - x1, y2 - y1), radius=radius, fill=fill)
    dst.alpha_composite(card, (x1 - 30, y1 - 30))
    inset = 24
    _paste_fit(dst, image, (x1 + inset, y1 + inset, x2 - inset, y2 - inset), cover=cover)


def _remove_light_background(src: Image.Image) -> Image.Image:
    im = src.convert("RGBA")
    data = []
    pixels = im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()
    for r, g, b, a in pixels:
        if r > 245 and g > 245 and b > 245:
            data.append((r, g, b, 0))
        else:
            data.append((r, g, b, a))
    im.putdata(data)
    return im


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
            frames.append(_remove_light_background(frame))
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
    if NOTIFICATION_SHOT.exists():
        return _notification_frame(index, size)

    if GPT_SCENE.exists():
        return _gpt_scene_frame(index, size)

    canvas = _gradient(size, (238, 244, 252), (253, 247, 241))
    draw = ImageDraw.Draw(canvas)
    w, h = size

    # macOS-like desktop chrome.
    draw.rectangle((0, 0, w, 36), fill=(255, 255, 255, 218))
    _text(draw, (24, 9), "PetGen", _font(FONT_BOLD, 16), (30, 41, 59))
    _text(draw, (1090, 9), "10:24  Thu", _font(FONT_MEDIUM, 15), (71, 85, 105))
    draw.rounded_rectangle((458, 650, 822, 704), radius=20, fill=(255, 255, 255, 175))
    for i, color in enumerate((INDIGO, SKY, GREEN, ROSE, AMBER)):
        draw.rounded_rectangle((492 + i * 62, 666, 530 + i * 62, 690), radius=8, fill=color + (210,))

    terminal_card = _shadow_card((670, 430), radius=24, fill=(18, 24, 42, 255))
    canvas.alpha_composite(terminal_card, (70, 112))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((120, 154, 730, 502), radius=18, fill=(15, 23, 42))
    draw.rounded_rectangle((120, 154, 730, 200), radius=18, fill=(30, 41, 59))
    draw.rectangle((120, 182, 730, 200), fill=(30, 41, 59))
    for i, color in enumerate(((248, 113, 113), (251, 191, 36), (52, 211, 153))):
        draw.ellipse((144 + i * 22, 170, 158 + i * 22, 184), fill=color)
    _text(draw, (150, 228), "$ petgen generate \\", _font(FONT_MEDIUM, 24), (226, 232, 240))
    _text(draw, (150, 268), '  --prompt "一只陪你写代码的桌面宠物"', _font(FONT_CJK, 22), (165, 180, 252))
    _text(draw, (150, 310), "$ petgen app", _font(FONT_MEDIUM, 24), (125, 211, 252))
    cursor = "█" if (index // 8) % 2 == 0 else " "
    _text(draw, (150, 382), f"桌宠已常驻桌面 {cursor}", _font(FONT_CJK, 28), (187, 247, 208))

    side = _shadow_card((330, 236), radius=24, fill=(255, 255, 255, 250))
    canvas.alpha_composite(side, (825, 112))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (878, 166), "AI 任务完成", _font(FONT_CJK, 30), INK)
    _text(draw, (880, 212), "切表情、弹气泡、发音效", _font(FONT_CJK, 18), MUTED)
    for y, label, color in ((264, "Codex", INDIGO), (306, "Claude Code", SKY), (348, "Antigravity", GREEN)):
        draw.rounded_rectangle((880, y, 1080, y + 30), radius=15, fill=color + (28,))
        draw.rounded_rectangle((880, y, 1080, y + 30), radius=15, outline=color + (180,), width=1)
        draw.ellipse((898, y + 10, 908, y + 20), fill=color)
        _text(draw, (920, y + 5), label, _font(FONT_MEDIUM, 16), INK)

    bubble_y = 426 + int(math.sin(index / 8) * 5)
    draw.rounded_rectangle((744, bubble_y, 1076, bubble_y + 78), radius=24, fill=(255, 255, 255, 248))
    draw.rounded_rectangle((744, bubble_y, 1076, bubble_y + 78), radius=24, outline=FAINT, width=1)
    draw.polygon(((1012, bubble_y + 74), (1052, bubble_y + 74), (1034, bubble_y + 104)), fill=(255, 255, 255, 248))
    _text(draw, (782, bubble_y + 18), "任务完成啦，休息一下？", _font(FONT_CJK, 23), INK)
    _text(draw, (784, bubble_y + 48), "我会在桌面陪你写代码。", _font(FONT_CJK, 17), MUTED)

    pet_scale = 235 + int(math.sin(index / 5) * 4)
    pet = _pet_on_stage(frame, (pet_scale, pet_scale))
    canvas.alpha_composite(pet, (1008, 450 + int(math.sin(index / 6) * 8)))
    return canvas.convert("RGB")


def _gpt_scene_frame(index: int, size=(1280, 720)) -> Image.Image:
    base = Image.open(GPT_SCENE).convert("RGBA")
    w, h = base.size
    # Gentle Ken Burns movement for the GIF/MP4 while keeping the still image crisp.
    zoom = 1.0 + 0.012 * math.sin(index / 18)
    crop_w = int(w / zoom)
    crop_h = int(h / zoom)
    left = (w - crop_w) // 2
    top = (h - crop_h) // 2
    scene = base.crop((left, top, left + crop_w, top + crop_h)).resize(size, Image.LANCZOS)
    draw = ImageDraw.Draw(scene)

    # Crisp text over the intentionally blank generated speech bubble.
    bubble_x = int(size[0] * 0.574)
    bubble_y = int(size[1] * 0.595)
    _text(draw, (bubble_x, bubble_y), "Codex 任务完成", _font(FONT_CJK, 22), INK)
    _text(draw, (bubble_x, bubble_y + 31), "变更已就绪，我在桌面陪你收尾。", _font(FONT_CJK, 14), MUTED)
    return scene.convert("RGB")


def _notification_frame(index: int, size=(1280, 720)) -> Image.Image:
    canvas = _gradient(size, (236, 246, 255), (247, 250, 252))
    shot = _required_image(NOTIFICATION_SHOT)
    w, h = size
    zoom = 1.0 + 0.01 * math.sin(index / 18)
    target_h = int(h * 0.86 * zoom)
    target_w = int(target_h * shot.width / shot.height)
    shot = shot.resize((target_w, target_h), Image.LANCZOS)
    x = (w - target_w) // 2
    y = (h - target_h) // 2 + int(6 * math.sin(index / 12))
    canvas.alpha_composite(shot, (x, y))
    return canvas.convert("RGB")


def _render_qt_panels(output_dir: Path) -> tuple[Path, Path, Path]:
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
    wide_usage_path = output_dir / "readme-ui-usage-wide.png"
    usage.resize(760, 360)
    app.processEvents()
    usage.grab().save(str(wide_usage_path))
    usage.close()
    return library_path, usage_path, wide_usage_path


def _make_ui_showcase(library_path: Path, usage_path: Path) -> Image.Image:
    canvas = _gradient((1280, 1540), (248, 250, 252), (239, 246, 255))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (72, 54), "真实运行，一屏看全", _font(FONT_CJK, 48), INK)
    _text(draw, (74, 124), "桌面通知、休息提醒、宠物中心、提醒列表、番茄钟和今日使用时长", _font(FONT_CJK, 24), MUTED)

    shots = (
        ("Codex 完成通知", _required_image(NOTIFICATION_SHOT), (72, 238, 616, 588), False),
        ("休息提醒", _required_image(REST_REMINDER_SHOT), (664, 238, 1208, 588), False),
        ("宠物中心", _required_image(PET_CENTER_SHOT), (72, 716, 616, 1066), False),
        ("提醒列表", _required_image(REMINDERS_SHOT), (664, 716, 1208, 1066), False),
        ("番茄钟", _required_image(POMODORO_SHOT), (72, 1194, 616, 1514), False),
        ("今日使用时长", _required_image(USAGE_SHOT), (664, 1194, 1208, 1514), False),
    )
    for title, image, box, cover in shots:
        _draw_image_panel(canvas, image, box, cover=cover)
        _text(draw, (box[0] + 18, box[1] - 40), title, _font(FONT_CJK, 24), INK)
    return canvas.convert("RGB")


def _make_showcase(desktop: Image.Image, ui: Image.Image) -> Image.Image:
    canvas = _gradient((1400, 1620), (248, 250, 252), (239, 246, 255))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (78, 54), "一句话生成，真的养在桌面上", _font(FONT_CJK, 58), INK)
    _text(draw, (82, 132), "桌面通知、休息提醒、宠物中心、番茄钟和今日使用时长都在真实运行。", _font(FONT_CJK, 25), MUTED)

    shots = (
        ("Codex 完成通知", _required_image(NOTIFICATION_SHOT), (90, 246, 660, 596), False),
        ("休息提醒", _required_image(REST_REMINDER_SHOT), (740, 246, 1310, 596), False),
        ("宠物中心", _required_image(PET_CENTER_SHOT), (90, 724, 660, 1074), False),
        ("提醒列表", _required_image(REMINDERS_SHOT), (740, 724, 1310, 1074), False),
        ("番茄钟", _required_image(POMODORO_SHOT), (90, 1202, 660, 1562), False),
        ("今日使用时长", _required_image(USAGE_SHOT), (740, 1202, 1310, 1562), False),
    )
    for title, image, box, cover in shots:
        _draw_image_panel(canvas, image, box, radius=34, cover=cover)
        _text(draw, (box[0] + 18, box[1] - 42), title, _font(FONT_CJK, 26), INK)
    return canvas.convert("RGB")


def _make_xhs_cover(desktop: Image.Image, ui: Image.Image) -> Image.Image:
    canvas = _gradient((1242, 1660), (239, 246, 255), (255, 247, 237))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (86, 104), "我把 AI 宠物", _font(FONT_CJK, 86), INK)
    _text(draw, (86, 206), "养在了桌面上", _font(FONT_CJK, 86), INK)
    _text(draw, (92, 326), "一句话生成  ·  托盘常驻  ·  编码任务会回应", _font(FONT_CJK, 34), MUTED)

    notification = _required_image(NOTIFICATION_SHOT)
    _draw_image_panel(canvas, notification, (88, 470, 520, 1018), radius=42)

    _draw_image_panel(canvas, _required_image(PET_CENTER_SHOT), (580, 516, 1120, 812), radius=38, cover=True)
    _draw_image_panel(canvas, _required_image(USAGE_SHOT), (580, 850, 1120, 1060), radius=38, cover=False)

    hero = Image.open(IMG_DIR / "pet-cat.png").convert("RGBA")
    hero.thumbnail((300, 300), Image.LANCZOS)
    canvas.alpha_composite(hero, (852, 296))

    _draw_image_panel(canvas, _required_image(REMINDERS_SHOT), (86, 1156, 560, 1484), radius=38)
    _draw_image_panel(canvas, _required_image(POMODORO_SHOT), (646, 1210, 1120, 1468), radius=38)
    return canvas.convert("RGB")


def _make_xhs_desktop(desktop: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", (1242, 1660), (248, 250, 252, 255))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (82, 86), "桌面运行效果", _font(FONT_CJK, 76), INK)
    _text(draw, (88, 186), "不是贴图预览，是真正能悬浮陪跑的宠物窗口", _font(FONT_CJK, 32), MUTED)
    _draw_image_panel(canvas, _required_image(NOTIFICATION_SHOT), (260, 302, 982, 1184), radius=44)
    frames = _load_idle_frames()
    for i in range(3):
        pet = _pet_on_stage(frames[(i * 2) % len(frames)], (210, 210))
        x = 190 + i * 330
        y = 1240 + int(math.sin(i) * 12)
        draw.rounded_rectangle((x - 20, y - 12, x + 220, y + 250), radius=34, fill=(255, 255, 255, 235))
        canvas.alpha_composite(pet, (x, y))
    return canvas.convert("RGB")


def _make_xhs_ui(ui: Image.Image, usage_path: Path) -> Image.Image:
    canvas = _gradient((1242, 1660), (255, 255, 255), (239, 246, 255))
    draw = ImageDraw.Draw(canvas)
    _text(draw, (82, 86), "桌宠也有工作台", _font(FONT_CJK, 76), INK)
    _text(draw, (88, 184), "宠物中心、提醒列表、番茄钟和今日使用时长都是真实窗口", _font(FONT_CJK, 32), MUTED)

    panels = (
        ("宠物中心", _required_image(PET_CENTER_SHOT), (78, 300, 1164, 720), True),
        ("提醒列表", _required_image(REMINDERS_SHOT), (78, 780, 586, 1154), False),
        ("番茄钟", _required_image(POMODORO_SHOT), (656, 804, 1164, 1130), False),
        ("今日使用时长", _required_image(USAGE_SHOT), (222, 1210, 1020, 1532), False),
    )
    for title, image, box, cover in panels:
        _draw_image_panel(canvas, image, box, radius=38, cover=cover)
        _text(draw, (box[0] + 18, box[1] - 40), title, _font(FONT_CJK, 26), INK)
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
        library_path, usage_path, wide_usage_path = _render_qt_panels(Path(tmp))
        ui = _make_ui_showcase(library_path, usage_path)
        showcase = _make_showcase(desktop, ui)

        desktop.save(paths.desktop_running, optimize=True)
        ui.save(paths.ui_showcase, optimize=True)
        showcase.save(paths.readme_showcase, optimize=True)
        _make_xhs_cover(desktop, ui).save(paths.xhs_cover, optimize=True)
        _make_xhs_desktop(desktop).save(paths.xhs_desktop, optimize=True)
        _make_xhs_ui(ui, wide_usage_path).save(paths.xhs_ui, optimize=True)
        _write_video_and_gif(desktop_frames, paths)

    for path in paths.__dict__.values():
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
