from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Events an interaction style can react to.
VOICE_CLIP_KINDS = ("tap", "happy", "alert", "busy", "error", "idle")

# Synthesized SFX keys produced by scripts/make_voice_sfx.py (public-domain, original).
SYNTH_SFX = ("pop", "chime_up", "chime_soft", "buzz", "tada", "tick")


@dataclass(frozen=True)
class InteractionStyle:
    id: str
    display_name: str
    emoji: str
    description: str = ""
    prompt_flavor: str = ""
    locale: str = ""  # BCP-47-ish, e.g. "zh_CN"; "" = any available voice
    voice: str = ""  # preferred installed voice name; "" = locale default
    lines: dict[str, tuple[str, ...]] = field(default_factory=dict)
    sounds: dict[str, str] = field(default_factory=dict)  # kind -> synth key or a wav filename
    # edge-tts (free online neural voice); empty string = use the system TTS fallback
    edge_voice: str = ""
    edge_rate: str = ""  # prosody rate e.g. +10% / -8%; empty = omit
    edge_pitch: str = ""  # prosody pitch e.g. +20Hz; empty = omit
    # Fish Audio public/custom voice model id. Empty means Fish Audio is not
    # configured for this style yet and the speaker should use the local preset.
    fish_reference_id: str = ""

    def line_for(self, kind: str) -> str | None:
        import random

        pool = self.lines.get(kind) or self.lines.get("tap") or ()
        if not pool:
            return None
        return random.choice(pool)

    def sound_for(self, kind: str) -> str | None:
        return self.sounds.get(kind)


def _sfx_path(pack_dir_name: str | None = None) -> Path:
    """Directory holding the synthesized (public-domain) SFX wav files."""
    return Path(__file__).resolve().parent / "resources" / "_sfx"


_BUILTIN: list[InteractionStyle] = [
    InteractionStyle(
        id="moe-pet",
        display_name="萌宠风",
        emoji="🐾",
        description="软萌陪伴、短句带喵，适合默认桌宠互动。",
        prompt_flavor="软萌的小动物陪伴感，短句、暖心、带一点喵。",
        locale="zh_CN",
        voice="婷婷",
        lines={
            "tap": (
                "喵～我在呢，陪你写代码喵。",
                "累了吗？伸个懒腰再继续喵。",
                "你超棒的，慢慢来喵。",
                "需要我安静陪着，还是聊两句喵？",
            ),
            "happy": ("太好啦喵！", "成功喽，奖励你一个喵～", "嘿嘿，干得漂亮喵！"),
            "alert": ("喵？该注意一下喽。", "提醒你来啦喵。"),
            "busy": ("正在忙喵，稍等哦。", "让我想想喵……"),
            "error": ("哎呀，出状况了喵。", "唔，好像不太对喵。"),
            "idle": ("……喵。", "呼噜噜喵。"),
        },
        sounds={
            "tap": "pop",
            "happy": "chime_up",
            "alert": "chime_soft",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-XiaoyiNeural",
        edge_rate="-8%",
        edge_pitch="+20Hz",
    ),
    InteractionStyle(
        id="moe-girl",
        display_name="萌妹风",
        emoji="🍬",
        description="甜一点、元气一点，完成任务时会积极打气。",
        prompt_flavor="甜美元气、爱鼓励、表达更轻快，像可靠又可爱的搭档。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": (
                "我在我在！今天也一起加油呀。",
                "嘿嘿，点到我啦。",
                "要不要先给自己一点小奖励？",
            ),
            "happy": ("搞定啦！你今天效率也太高了吧！", "完成完成，超漂亮！", "好耶，这一步拿下！"),
            "alert": ("叮咚，有件事要看一下哦。", "提醒来啦，别错过。"),
            "busy": ("处理中，马上就好。", "我在盯着进度呢。"),
            "error": ("欸，好像卡住了，我们看一下。", "出错啦，但问题不大，慢慢查。"),
            "idle": ("我乖乖待机中。", "需要我就点我一下呀。"),
        },
        sounds={
            "tap": "pop",
            "happy": "tada",
            "alert": "chime_up",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-XiaoxiaoNeural",
        edge_rate="+12%",
        edge_pitch="+35Hz",
    ),
    InteractionStyle(
        id="elegant-senior",
        display_name="御姐风",
        emoji="🌙",
        description="成熟、从容、略带调侃，适合长任务完成提示。",
        prompt_flavor="成熟从容、简洁、有一点轻调侃，像稳得住场面的搭档。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": ("我在。慢慢说，别急。", "想让我看什么？", "状态不错，继续保持。"),
            "happy": (
                "任务完成。不错，这次处理得很利落。",
                "收尾得很好，可以进入下一步了。",
                "很好，结果已经稳住了。",
            ),
            "alert": ("留意一下，有事需要处理。", "该看一眼了，别拖太久。"),
            "busy": ("处理中，先别急着打断。", "让我把这段跑完。"),
            "error": ("这里出问题了。别慌，先看关键错误。", "异常出现了，先定位根因。"),
            "idle": ("安静待命。", "需要时叫我。"),
        },
        sounds={
            "tap": "chime_soft",
            "happy": "chime_up",
            "alert": "tick",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-TW-HsiaoChenNeural",
        edge_rate="-10%",
        edge_pitch="-18Hz",
    ),
    InteractionStyle(
        id="butler",
        display_name="管家风",
        emoji="🎩",
        description="克制、礼貌、信息密度高，偏工具型提醒。",
        prompt_flavor="礼貌克制、短句、重视状态和结果，像专业管家。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": ("我在。", "需要的时候叫我。", "休息也是进度的一部分。"),
            "happy": ("任务已完成，结果已为您记录。", "如预期完成。", "本轮工作已结束。"),
            "alert": ("提醒您留意。", "有一件事需要关注。"),
            "busy": ("请稍候。", "正在处理。"),
            "error": ("出现了异常。", "此处需要检查。"),
            "idle": ("静候吩咐。", "待命中。"),
        },
        sounds={
            "tap": "chime_soft",
            "happy": "chime_up",
            "alert": "tick",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-YunyangNeural",
        edge_rate="-10%",
        edge_pitch="-25Hz",
    ),
    InteractionStyle(
        id="tsundere",
        display_name="傲娇风",
        emoji="💢",
        description="嘴硬但关心，点击互动更有戏。",
        prompt_flavor="傲娇、嘴上嫌弃但很关心，句子短，有一点可爱的别扭感。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": (
                "哼，才不是特意等你点的。",
                "别误会，我只是刚好在。",
                "……看在你这么努力的份上，陪你一下。",
            ),
            "happy": (
                "哼，还算顺利吧，我可没特意等你完成。",
                "完成了？还不错嘛。",
                "勉强算你这次处理得漂亮。",
            ),
            "alert": ("喂，该看提醒了，别装没听见。", "有事来了，快处理一下。"),
            "busy": ("等一下啦，正在处理。", "别催，我看着呢。"),
            "error": ("笨蛋，出错了啦。先看日志。", "这里不对，别硬跑了。"),
            "idle": ("……才没有无聊。", "我只是在待机而已。"),
        },
        sounds={
            "tap": "pop",
            "happy": "tada",
            "alert": "chime_up",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-YunxiaNeural",
        edge_rate="+8%",
        edge_pitch="+15Hz",
    ),
]

_LEGACY_STYLE_IDS = {
    "soft-meow": "moe-pet",
    "energetic-zap": "moe-girl",
    "calm-butler": "butler",
    "warm": "moe-pet",
    "cheerful": "moe-girl",
    "calm": "butler",
}


def load_styles() -> dict[str, InteractionStyle]:
    """Return the built-in interaction styles keyed by id."""
    return {style.id: style for style in _BUILTIN}


def default_style() -> InteractionStyle:
    return _BUILTIN[0]


def normalize_style_id(value: str | None) -> str:
    styles = load_styles()
    if value in styles:
        return str(value)
    mapped = _LEGACY_STYLE_IDS.get(str(value or ""))
    if mapped in styles:
        return mapped
    return default_style().id
