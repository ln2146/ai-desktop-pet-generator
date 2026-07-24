from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
from typing import Callable

from petgen.sound import SoundService
from petgen.voicepack import VoicePack, default_pack, load_catalog

log = logging.getLogger(__name__)

# --- optional backends: degrade gracefully when missing ---------------------

try:  # QTextToSpeech needs a speech plugin; used as the offline fallback voice
    from PySide6.QtTextToSpeech import QTextToSpeech

    _HAS_TTS = True
except Exception:  # pragma: no cover - import-time branch
    QTextToSpeech = None  # type: ignore[assignment]
    _HAS_TTS = False

try:  # edge-tts: free online neural TTS (the preferred, expressive voice)
    import edge_tts

    _HAS_EDGE_LIB = True
except Exception:  # pragma: no cover - import-time branch
    edge_tts = None  # type: ignore[assignment]
    _HAS_EDGE_LIB = False

try:  # QMediaPlayer is needed to play the mp3 that edge-tts produces
    from PySide6.QtCore import QObject, QUrl, Signal
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    _HAS_QT_MEDIA = True
except Exception:  # pragma: no cover - import-time branch
    QObject = object  # type: ignore[assignment]
    Signal = None  # type: ignore[assignment]
    QUrl = QAudioOutput = QMediaPlayer = None  # type: ignore[assignment]
    _HAS_QT_MEDIA = False

# edge is usable only when both the library and a media player are available
_HAS_EDGE = _HAS_EDGE_LIB and _HAS_QT_MEDIA


class _SystemSpeaker:
    """QTextToSpeech wrapper (offline fallback). Speaks in a pack's voice/locale."""

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


if _HAS_EDGE:

    class _EdgeSpeaker(QObject):  # type: ignore[misc,valid-type]
        """Synthesize speech with edge-tts off-thread, play the mp3 on the GUI thread.

        Synthesis runs in a daemon thread (asyncio); the resulting file path is handed
        back through a queued signal so QMediaPlayer only ever runs on the main thread.
        On any failure it emits ``_fallback`` so the system TTS reads the line instead.
        """

        _ready = Signal(str)
        _fallback = Signal(str)

        def __init__(self, fallback_fn: Callable[[str], bool]) -> None:
            super().__init__()
            self._fallback_fn = fallback_fn
            self._player = None
            self._current_tmp: str | None = None
            self._token = 0
            self._ready.connect(self._play)
            self._fallback.connect(self._do_fallback)

        def stop(self) -> None:
            if self._player is not None:
                try:
                    self._player.stop()
                except Exception:
                    pass

        def speak(self, text: str, voice: str, rate: str = "", pitch: str = "") -> bool:
            if not text or not voice:
                return False
            self._token += 1
            token = self._token
            self.stop()
            threading.Thread(
                target=self._synthesize, args=(text, voice, rate, pitch, token), daemon=True
            ).start()
            return True

        def _synthesize(self, text: str, voice: str, rate: str, pitch: str, token: int) -> None:
            path: str | None = None
            try:
                fd, path = tempfile.mkstemp(suffix=".mp3", prefix="petgen-tts-")
                os.close(fd)
                asyncio.run(self._save(text, voice, rate, pitch, path))
                if token != self._token:  # a newer speak() superseded this one
                    self._unlink(path)
                    return
                self._ready.emit(path)
            except Exception:
                log.debug("edge-tts synthesis failed, falling back to system TTS", exc_info=True)
                if path is not None:
                    self._unlink(path)
                self._fallback.emit(text)

        async def _save(self, text: str, voice: str, rate: str, pitch: str, path: str) -> None:
            kwargs: dict[str, str] = {"text": text, "voice": voice}
            if rate:
                kwargs["rate"] = rate
            if pitch:
                kwargs["pitch"] = pitch
            comm = edge_tts.Communicate(**kwargs)
            await comm.save(path)

        def _play(self, path: str) -> None:
            try:
                self._ensure_player()
                if self._player is None:
                    raise RuntimeError("no media player")
                self._current_tmp = path
                self._player.setSource(QUrl.fromLocalFile(path))
                self._player.play()
            except Exception:
                log.debug("edge-tts playback failed", exc_info=True)
                self._unlink(path)

        def _ensure_player(self) -> None:
            if self._player is not None:
                return
            player = QMediaPlayer()
            player.setAudioOutput(QAudioOutput())
            player.mediaStatusChanged.connect(self._on_status)
            self._player = player

        def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
            try:
                ended = status == QMediaPlayer.MediaStatus.EndOfMedia
            except Exception:
                ended = False
            if ended and self._current_tmp is not None:
                self._unlink(self._current_tmp)
                self._current_tmp = None

        def _do_fallback(self, text: str) -> None:
            try:
                self._fallback_fn(text)
            except Exception:
                log.debug("system TTS fallback failed", exc_info=True)

        @staticmethod
        def _unlink(path: str) -> None:
            try:
                os.unlink(path)
            except OSError:
                pass

else:

    class _EdgeSpeaker:  # type: ignore[no-redef]
        """Stub used when edge-tts or QtMultimedia is unavailable: never speaks."""

        def __init__(self, fallback_fn: Callable[[str], bool] | None = None) -> None:
            self._fallback_fn = fallback_fn

        def speak(self, text: str, voice: str, rate: str = "", pitch: str = "") -> bool:
            return False

        def stop(self) -> None:
            pass


class Speaker:
    """Facade: prefer edge-tts for expressive voices, fall back to system TTS."""

    def __init__(self) -> None:
        self._system = _SystemSpeaker()
        self._edge: _EdgeSpeaker | None = _EdgeSpeaker(fallback_fn=self._system.speak) if _HAS_EDGE else None
        self._edge_voice = ""
        self._edge_rate = ""
        self._edge_pitch = ""

    @property
    def available(self) -> bool:
        return _HAS_EDGE or self._system.available

    def apply_pack(self, pack: VoicePack) -> None:
        self._edge_voice = pack.edge_voice
        self._edge_rate = pack.edge_rate
        self._edge_pitch = pack.edge_pitch
        self._system.apply_pack(pack)

    def speak(self, text: str | None) -> bool:
        if not text:
            return False
        if (
            self._edge is not None
            and self._edge_voice
            and self._edge.speak(text, self._edge_voice, self._edge_rate, self._edge_pitch)
        ):
            return True  # edge accepted; if synthesis later fails it falls back internally
        return self._system.speak(text)


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
