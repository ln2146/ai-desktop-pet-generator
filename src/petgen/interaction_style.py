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
        description="轻快、软糯、短促的小宠物陪伴感，适合默认桌宠互动。",
        prompt_flavor="软萌的小动物陪伴感，短句、轻快、亲近但不装人设；少量拟声，不固定猫叫。",
        locale="zh_CN",
        voice="婷婷",
        lines={
            "tap": (
                "在呢，蹭一下。",
                "呼噜，陪你一会儿。",
                "累了吗？伸个懒腰再继续。",
                "收到，尾巴摇起来了。",
            ),
            "happy": ("完成啦，蹦一下！", "好耶，奖励一颗小星星。", "做得漂亮，尾巴都摇快了。"),
            "alert": ("叮，有件事要看一下。", "小提醒到啦，别错过。"),
            "busy": ("处理中，爪爪按住进度。", "我在看着呢，马上好。"),
            "error": ("哎呀，卡住了，我们看一眼。", "唔，这里不太对，先别急。"),
            "idle": ("呼噜呼噜。", "我乖乖待机。"),
        },
        sounds={
            "tap": "pop",
            "happy": "chime_up",
            "alert": "chime_soft",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-XiaoyiNeural",
        edge_rate="+8%",
        edge_pitch="+28Hz",
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
        description="低一点、稳一点，温柔但有掌控感，适合长任务和结果提示。",
        prompt_flavor="成熟、冷静、温柔有边界，像可靠的成熟女性搭档；少撒娇，少命令，多给清晰判断。",
        locale="zh_CN",
        voice="婷婷",
        lines={
            "tap": ("嗯，我在。说重点就好。", "交给我看一下。", "状态不错，继续推进。"),
            "happy": (
                "完成了。结果干净，收得漂亮。",
                "这一轮稳稳落地，可以进入下一步。",
                "不错，关键部分已经处理妥当。",
            ),
            "alert": ("提醒到了，先看最要紧的那一件。", "这里需要你看一眼。"),
            "busy": ("我在处理，先让它跑完。", "进度还在走，稍等一下。"),
            "error": ("这里出问题了。别急，先抓关键错误。", "异常出现了，我们先定位根因。"),
            "idle": ("我在旁边待命。", "需要时叫我就好。"),
        },
        sounds={
            "tap": "chime_soft",
            "happy": "chime_up",
            "alert": "tick",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-XiaoxiaoNeural",
        edge_rate="-8%",
        edge_pitch="-2Hz",
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
