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
    locale_en: str = "en_US"
    voice_en: str = ""
    lines: dict[str, tuple[str, ...]] = field(default_factory=dict)
    lines_en: dict[str, tuple[str, ...]] = field(default_factory=dict)
    sounds: dict[str, str] = field(default_factory=dict)  # kind -> synth key or a wav filename
    # edge-tts (free online neural voice); empty string = use the system TTS fallback
    edge_voice: str = ""
    edge_rate: str = ""  # prosody rate e.g. +10% / -8%; empty = omit
    edge_pitch: str = ""  # prosody pitch e.g. +20Hz; empty = omit
    edge_voice_en: str = ""
    edge_rate_en: str = ""
    edge_pitch_en: str = ""

    def line_for(self, kind: str, language: str = "zh_CN") -> str | None:
        import random

        lines = self.lines_en if _is_english(language) and self.lines_en else self.lines
        pool = lines.get(kind) or lines.get("tap") or ()
        if not pool:
            return None
        return random.choice(pool)

    def sound_for(self, kind: str) -> str | None:
        return self.sounds.get(kind)

    def locale_for(self, language: str = "zh_CN") -> str:
        return self.locale_en if _is_english(language) and self.locale_en else self.locale

    def voice_for(self, language: str = "zh_CN") -> str:
        return self.voice_en if _is_english(language) and self.voice_en else self.voice

    def edge_voice_for(self, language: str = "zh_CN") -> str:
        if _is_english(language) and self.edge_voice_en:
            return self.edge_voice_en
        return self.edge_voice

    def edge_rate_for(self, language: str = "zh_CN") -> str:
        if _is_english(language) and self.edge_rate_en:
            return self.edge_rate_en
        return self.edge_rate

    def edge_pitch_for(self, language: str = "zh_CN") -> str:
        if _is_english(language) and self.edge_pitch_en:
            return self.edge_pitch_en
        return self.edge_pitch


def _is_english(language: str | None) -> bool:
    return str(language or "").lower().startswith("en")


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
        lines_en={
            "tap": ("I'm here with you.", "Still here.", "Need a tiny pause?", "Got it. Easy does it."),
            "happy": ("Done. Nice work.", "Yay, that step is clear.", "Lovely. Keep going."),
            "alert": ("Ping, a reminder is here.", "There's something to check."),
            "busy": ("Working on it. One sec.", "I'm watching the progress."),
            "error": ("Hmm, it got stuck.", "Something looks off. Let's check."),
            "idle": ("I'm on standby.", "Call me when you need me."),
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
        edge_voice_en="en-US-AnaNeural",
        edge_rate_en="+8%",
        edge_pitch_en="+18Hz",
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
        lines_en={
            "tap": ("I'm here, let's do this.", "Hey, you called?", "Want a tiny reward first?"),
            "happy": ("Done. That was beautiful.", "All set, great pace!", "Yes, this step is ours."),
            "alert": ("Ding, something needs a look.", "Reminder's here. Don't miss it."),
            "busy": ("Processing. Almost there.", "I'm keeping an eye on it."),
            "error": ("Looks like we're stuck. Let's check.", "It errored, but we'll trace it slowly."),
            "idle": ("I'm standing by.", "Tap me when you need me."),
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
        edge_voice_en="en-US-JennyNeural",
        edge_rate_en="+6%",
        edge_pitch_en="+12Hz",
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
        lines_en={
            "tap": ("I'm here. Give me the essentials.", "Let me take a look.", "Good state. Keep moving."),
            "happy": (
                "Done. Clean result, nicely wrapped.",
                "This round landed well. Move to the next step.",
                "Good. The key part is handled.",
            ),
            "alert": ("Reminder's in. Check the most important one first.", "This needs your attention."),
            "busy": ("I'm handling it. Let it finish.", "Progress is moving. One moment."),
            "error": ("Something broke here. Start with the key error.", "There's an exception. Let's find the root cause."),
            "idle": ("I'm nearby on standby.", "Call me when needed."),
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
        edge_voice_en="en-US-AriaNeural",
        edge_rate_en="-6%",
        edge_pitch_en="-2Hz",
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
        lines_en={
            "tap": ("I'm here. Please go ahead.", "What would you like handled?", "I'll remain on standby."),
            "happy": ("Completed. The result is ready.", "Task complete. You may proceed.", "This round is finished."),
            "alert": ("Reminder received. Please note it.", "One item needs your confirmation."),
            "busy": ("Please wait. I'm processing it.", "Processing now. Results shortly."),
            "error": ("An error occurred. Check the key error.", "This needs root-cause confirmation first."),
            "idle": ("I'm on standby.", "Call me when needed."),
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
        edge_voice_en="en-GB-ThomasNeural",
        edge_rate_en="-4%",
        edge_pitch_en="-4Hz",
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
        lines_en={
            "tap": ("I'm here. What's up?", "Alright, let's take a look.", "Looks steady. Keep going.", "Want me to watch it?"),
            "happy": ("Done. Looks good.", "This step is cleared. Keep moving.", "Finished. Nice and steady."),
            "alert": ("Reminder's here. Take a look.", "Something needs handling."),
            "busy": ("Processing. Give it a sec.", "I'm running this part. Results soon."),
            "error": ("This got stuck. Check the key error first.", "Something broke. Let's split it up."),
            "idle": ("I'm on standby.", "Call me when needed."),
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
        edge_voice_en="en-US-AndrewNeural",
        edge_rate_en="+4%",
        edge_pitch_en="+2Hz",
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
        lines_en={
            "tap": ("I'm here. Take your time.", "No rush. Start with the point.", "Still steady. Keep looking.", "Want me to help sort it out?"),
            "happy": (
                "Done. That was handled steadily.",
                "The result has landed. You can wrap it up.",
                "Good round. Keep the rhythm.",
            ),
            "alert": ("Reminder's in. Check the important part first.", "This needs your confirmation."),
            "busy": ("I'm processing it. Let it finish.", "Progress is moving. Give it a moment."),
            "error": ("There's an issue. Start with the root cause.", "Don't rush. Find the key error first."),
            "idle": ("I'm nearby on standby.", "Call me when needed."),
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
        edge_voice_en="en-US-BrianNeural",
        edge_rate_en="-4%",
        edge_pitch_en="-6Hz",
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
        lines_en={
            "tap": (
                "Hmph, I wasn't waiting for you.",
                "Don't get the wrong idea. I was just here.",
                "Fine, I'll keep you company for a bit.",
            ),
            "happy": (
                "Hmph. Smooth enough, I guess.",
                "Done? Not bad.",
                "I'll admit, that was handled pretty well.",
            ),
            "alert": ("Hey, check the reminder. Don't ignore it.", "Something came up. Deal with it."),
            "busy": ("Wait a second. I'm processing it.", "Don't rush me. I'm watching it."),
            "error": ("Dummy, it errored. Check the logs first.", "This is wrong. Stop forcing it."),
            "idle": ("...I'm not bored.", "I'm just on standby, that's all."),
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
        edge_voice_en="en-US-EricNeural",
        edge_rate_en="+6%",
        edge_pitch_en="+6Hz",
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
