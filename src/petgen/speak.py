from __future__ import annotations

from petgen.sound import SoundService
from petgen.voicepack import VoicePack, default_pack, load_catalog

try:  # QTextToSpeech needs a speech plugin; degrade gracefully if absent
    from PySide6.QtTextToSpeech import QTextToSpeech

    _HAS_TTS = True
except Exception:  # pragma: no cover - import-time branch
    QTextToSpeech = None  # type: ignore[assignment]
    _HAS_TTS = False


class Speaker:
    """Thin QTextToSpeech wrapper that speaks a pack's lines in its voice."""

    def __init__(self) -> None:
        self._tts = None
        self._available = False
        if _HAS_TTS:
            try:
                self._tts = QTextToSpeech()
                self._available = len(self._tts.availableVoices()) > 0
            except Exception:
                self._tts = None
                self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def apply_pack(self, pack: VoicePack) -> None:
        if not self._available or self._tts is None:
            return
        try:
            voices = self._tts.availableVoices()
            chosen = None
            if pack.voice:
                for v in voices:
                    if v.name() == pack.voice:
                        chosen = v
                        break
            if chosen is None and pack.locale:
                for v in voices:
                    loc = v.locale()
                    if loc.name() == pack.locale or loc.bcp47Name() == pack.locale:
                        chosen = v
                        break
            if chosen is None and voices:
                chosen = voices[0]
            if chosen is not None:
                self._tts.setVoice(chosen)
        except Exception:
            pass

    def speak(self, text: str | None) -> bool:
        if not text or not self._available or self._tts is None:
            return False
        try:
            self._tts.say(text)
            return True
        except Exception:
            return False


def available_voice_names() -> list[str]:
    """Installed voice names (for the settings UI / diagnostics)."""
    if not _HAS_TTS:
        return []
    try:
        tts = QTextToSpeech()
        return [v.name() for v in tts.availableVoices()]
    except Exception:
        return []


class VoicePackService:
    """Coordinates SFX + TTS for the selected voice pack."""

    def __init__(self, pack: VoicePack | None = None, *, enabled: bool = True) -> None:
        self._catalog = load_catalog()
        self._pack = pack or default_pack()
        self._enabled = enabled
        self._sound = SoundService()
        self._speaker = Speaker()
        self._sound.set_enabled(enabled)
        self._speaker.apply_pack(self._pack)

    @property
    def pack(self) -> VoicePack:
        return self._pack

    @property
    def catalog(self) -> dict[str, VoicePack]:
        return self._catalog

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._sound.set_enabled(enabled)

    def set_pack(self, pack_id: str) -> VoicePack:
        pack = self._catalog.get(pack_id) or default_pack()
        self._pack = pack
        self._speaker.apply_pack(pack)
        return pack

    def react(self, kind: str) -> dict[str, bool]:
        """Play the pack's SFX and speak a line for ``kind``. Returns what fired."""
        result = {"sfx": False, "speech": False}
        if not self._enabled:
            return result
        result["sfx"] = self._sound.play(self._pack.sound_for(kind))
        line = self._pack.line_for(kind)
        result["speech"] = self._speaker.speak(line)
        return result

    def preview(self) -> dict[str, bool]:
        return self.react("tap")
