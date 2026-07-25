from __future__ import annotations

from petgen.interaction_style import (
    SYNTH_SFX as SYNTH_SFX,
)
from petgen.interaction_style import (
    VOICE_CLIP_KINDS as VOICE_CLIP_KINDS,
)
from petgen.interaction_style import (
    InteractionStyle,
    default_style,
    load_styles,
    normalize_style_id,
)
from petgen.interaction_style import (
    _sfx_path as _sfx_path,
)

# Backward-compatible names for the audio layer and older tests. A former
# "voice pack" is now an interaction style: lines, TTS voice, prosody and SFX
# are intentionally bound together.
VoicePack = InteractionStyle


def load_catalog() -> dict[str, VoicePack]:
    """Return built-in interaction styles keyed by id."""
    return load_styles()


def default_pack() -> VoicePack:
    return default_style()


def normalize_pack_id(value: str | None) -> str:
    return normalize_style_id(value)
