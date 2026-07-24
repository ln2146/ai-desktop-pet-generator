from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Events a voice pack can react to.
VOICE_CLIP_KINDS = ("tap", "happy", "alert", "busy", "error", "idle")

# Synthesized SFX keys produced by scripts/make_voice_sfx.py (public-domain, original).
SYNTH_SFX = ("pop", "chime_up", "chime_soft", "buzz", "tada", "tick")


@dataclass(frozen=True)
class VoicePack:
    id: str
    display_name: str
    emoji: str
    locale: str = ""  # BCP-47-ish, e.g. "zh_CN"; "" = any available voice
    voice: str = ""  # preferred installed voice name; "" = locale default
    lines: dict[str, tuple[str, ...]] = field(default_factory=dict)
    sounds: dict[str, str] = field(default_factory=dict)  # kind -> synth key or a wav filename
    # edge-tts (free online neural voice); empty string = use the system TTS fallback
    edge_voice: str = ""
    edge_rate: str = ""  # prosody rate e.g. +10% / -8%; empty = omit
    edge_pitch: str = ""  # prosody pitch e.g. +5%; empty = omit

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


_BUILTIN: list[VoicePack] = [
    VoicePack(
        id="soft-meow",
        display_name="软萌喵",
        emoji="🐱",
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
        sounds={"tap": "pop", "happy": "chime_up", "alert": "chime_soft", "busy": "tick", "error": "buzz"},
        edge_voice="zh-CN-XiaoyiNeural",
        edge_rate="-5%",
        edge_pitch="+5%",
    ),
    VoicePack(
        id="energetic-zap",
        display_name="元气电波",
        emoji="⚡",
        locale="zh_CN",
        voice="",
        lines={
            "tap": ("冲冲冲！今天也要加油喵！", "嘿嘿，点到我了喵～", "来击个掌喵！"),
            "happy": ("耶！成功啦！", "太厉害了喵！", "满分满分喵！"),
            "alert": ("注意注意喵！", "叮！提醒来咯喵！"),
            "busy": ("火力全开喵！", "正在处理中喵～"),
            "error": ("呜，卡壳了喵！", "报错啦，别慌喵！"),
            "idle": ("待机中喵！", "充电完毕喵～"),
        },
        sounds={"tap": "pop", "happy": "tada", "alert": "chime_up", "busy": "tick", "error": "buzz"},
        edge_voice="zh-CN-XiaoxiaoNeural",
        edge_rate="+10%",
        edge_pitch="+3%",
    ),
    VoicePack(
        id="calm-butler",
        display_name="沉稳管家",
        emoji="🎩",
        locale="zh_CN",
        voice="",
        lines={
            "tap": ("嗯，我在。", "需要的时候叫我。", "休息也是进度的一部分。"),
            "happy": ("做得很好。", "如预期完成。", "值得肯定。"),
            "alert": ("提醒您留意。", "有一件事需要关注。"),
            "busy": ("请稍候。", "正在处理。"),
            "error": ("出现了异常。", "此处需要检查。"),
            "idle": ("……", "静候吩咐。"),
        },
        sounds={"tap": "chime_soft", "happy": "chime_up", "alert": "tick", "busy": "tick", "error": "buzz"},
        edge_voice="zh-CN-YunxiNeural",
        edge_rate="-8%",
        edge_pitch="-2%",
    ),
]


def load_catalog() -> dict[str, VoicePack]:
    """Return the built-in voice packs keyed by id."""
    return {pack.id: pack for pack in _BUILTIN}


def default_pack() -> VoicePack:
    return _BUILTIN[0]
