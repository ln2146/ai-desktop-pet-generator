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
        description="柔软、轻快、陪伴感强，适合默认桌宠互动。",
        prompt_flavor="软萌的小宠物陪伴感，短句、轻快、自然；少用拟声和肢体词，避免听起来像硬装动物。",
        locale="zh_CN",
        voice="婷婷",
        lines={
            "tap": (
                "在呢，陪你。",
                "嗯，我在旁边。",
                "累了吗？缓一缓。",
                "收到，慢慢来。",
            ),
            "happy": ("完成啦，好棒。", "好耶，这步过啦。", "漂亮，继续保持。"),
            "alert": ("叮，提醒到啦。", "有件事要看一下。"),
            "busy": ("处理中，稍等呀。", "我在看着进度。"),
            "error": ("唔，卡住了。", "这里不太对，我们看看。"),
            "idle": ("我在待机。", "需要就叫我。"),
        },
        sounds={
            "tap": "pop",
            "happy": "chime_up",
            "alert": "chime_soft",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-XiaoyiNeural",
        edge_rate="+6%",
        edge_pitch="+18Hz",
    ),
    InteractionStyle(
        id="moe-girl",
        display_name="萌妹风",
        emoji="🍬",
        description="甜美元气的人类搭档感，完成任务时会积极打气。",
        prompt_flavor="甜美元气、爱鼓励、表达轻快清楚，像可靠的人类搭档；不要拟动物化。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": (
                "我在我在，一起加油呀。",
                "嘿嘿，叫我啦。",
                "要不要先给自己一点小奖励？",
            ),
            "happy": ("搞定啦，这一步很漂亮。", "完成完成，状态超好！", "好耶，这一步拿下。"),
            "alert": ("叮咚，有件事要看一下哦。", "提醒来啦，别错过呀。"),
            "busy": ("处理中，马上就好。", "我在盯着进度呢。"),
            "error": ("欸，好像卡住了，我们看一下。", "出错啦，先慢慢查。"),
            "idle": ("我在待机中。", "需要我就点我一下呀。"),
        },
        sounds={
            "tap": "pop",
            "happy": "tada",
            "alert": "chime_up",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-XiaoxiaoNeural",
        edge_rate="+6%",
        edge_pitch="+18Hz",
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
        description="克制、礼貌、清楚，偏专业助理型状态提示。",
        prompt_flavor="礼貌克制、短句、重视状态和下一步，像专业助理；自然表达，避免过度机械、低沉或播报腔。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": ("我在，请说。", "需要我处理什么？", "我会保持待命。"),
            "happy": ("已完成，结果可以使用。", "任务完成，可以进入下一步。", "本轮处理结束。"),
            "alert": ("提醒到了，请留意。", "有一件事需要您确认。"),
            "busy": ("请稍候，我正在处理。", "正在处理中，很快给您结果。"),
            "error": ("出现异常，请查看关键错误。", "这里需要先确认根因。"),
            "idle": ("我在待命。", "需要时请叫我。"),
        },
        sounds={
            "tap": "chime_soft",
            "happy": "chime_up",
            "alert": "tick",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-YunxiNeural",
        edge_rate="-2%",
        edge_pitch="-4Hz",
    ),
    InteractionStyle(
        id="sunny-boy",
        display_name="清爽男声",
        emoji="☀️",
        description="清爽、直接、有伙伴感的男生语音，适合日常工作提醒。",
        prompt_flavor="清爽自然、直接可靠，像同龄男生搭档；语气积极但不过度热血，不命令、不油腻。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": (
                "我在，说吧。",
                "来了，看看什么事。",
                "状态还行，继续推进。",
                "需要我帮你盯一下吗？",
            ),
            "happy": (
                "搞定，结果不错。",
                "这一步拿下了，可以继续。",
                "完成了，收得挺稳。",
            ),
            "alert": ("提醒到了，看一眼吧。", "有件事需要处理一下。"),
            "busy": ("处理中，稍等一下。", "我在跑这段，马上看结果。"),
            "error": ("这里卡住了，先看关键错误。", "出问题了，我们拆开看。"),
            "idle": ("我在待命。", "需要时叫我。"),
        },
        sounds={
            "tap": "pop",
            "happy": "chime_up",
            "alert": "chime_soft",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-YunjianNeural",
        edge_rate="+4%",
        edge_pitch="+2Hz",
    ),
    InteractionStyle(
        id="steady-senior",
        display_name="沉稳男声",
        emoji="🌲",
        description="沉稳、耐心、有经验感的男声，适合长任务和错误定位提示。",
        prompt_flavor="沉稳自然、耐心可靠，像有经验的前辈搭档；少口号、少敬语，给判断和下一步。",
        locale="zh_CN",
        voice="",
        lines={
            "tap": (
                "我在，慢慢说。",
                "先别急，讲重点。",
                "状态还稳，继续看。",
                "需要我一起梳理吗？",
            ),
            "happy": (
                "完成了，处理得很稳。",
                "结果已经落地，可以收尾。",
                "这一轮不错，继续保持节奏。",
            ),
            "alert": ("提醒到了，先看重要的。", "这里需要你确认一下。"),
            "busy": ("我在处理，等它跑完。", "进度还在走，稍等片刻。"),
            "error": ("这里有异常，先看根因。", "别急，先把关键错误找出来。"),
            "idle": ("我在旁边待命。", "需要时叫我。"),
        },
        sounds={
            "tap": "chime_soft",
            "happy": "chime_up",
            "alert": "tick",
            "busy": "tick",
            "error": "buzz",
        },
        edge_voice="zh-CN-YunyangNeural",
        edge_rate="-4%",
        edge_pitch="-8Hz",
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
