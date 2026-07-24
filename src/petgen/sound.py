from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from petgen.datadir import data_dir
from petgen.voicepack import SYNTH_SFX, _sfx_path

SAMPLE_RATE = 22050


# --- synthesis (pure python; output is original -> public domain) -----------


def _write_wav(path: Path, samples: list[float], rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(s) for s in samples), default=1.0) or 1.0
    scale = 32767.0 / max(1.0, peak)
    ints = [max(-32768, min(32767, int(s * scale))) for s in samples]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{len(ints)}h", *ints))


def _envelope(i: int, n: int, attack: int, decay: int) -> float:
    if i < attack:
        return i / attack
    if i > n - decay:
        return max(0.0, (n - i) / decay)
    return 1.0


def _tone(
    freq: float,
    duration: float,
    *,
    volume: float = 0.6,
    wave_kind: str = "sine",
    attack: float = 0.005,
    decay: float = 0.05,
    glide_to: float | None = None,
    rate: int = SAMPLE_RATE,
) -> list[float]:
    n = int(duration * rate)
    a = max(1, int(attack * rate))
    d = max(1, int(decay * rate))
    out: list[float] = []
    for i in range(n):
        t = i / rate
        f = freq if glide_to is None else freq + (glide_to - freq) * (i / max(1, n - 1))
        phase = 2 * math.pi * f * t
        v = math.sin(phase) if wave_kind == "sine" else (1.0 if math.sin(phase) >= 0 else -1.0)
        out.append(v * volume * _envelope(i, n, a, d))
    return out


def _mix(*tracks: list[float]) -> list[float]:
    n = max((len(t) for t in tracks), default=0)
    out = [0.0] * n
    for t in tracks:
        for i, s in enumerate(t):
            out[i] += s
    return out


def _stagger(parts: list[tuple[float, list[float]]], rate: int = SAMPLE_RATE) -> list[float]:
    """Place each (start_seconds, samples) part on a timeline and mix."""
    total = max((int(start * rate) + len(s) for start, s in parts), default=0)
    out = [0.0] * total
    for start, s in parts:
        offset = int(start * rate)
        for i, v in enumerate(s):
            out[offset + i] += v
    return out


def _build(name: str) -> list[float]:
    if name == "pop":
        return _tone(660, 0.12, volume=0.7, glide_to=300, decay=0.08)
    if name == "chime_up":
        return _mix(_tone(880, 0.3, volume=0.5, decay=0.2), _tone(1320, 0.3, volume=0.4, decay=0.2))
    if name == "chime_soft":
        return _tone(523.25, 0.4, volume=0.4, decay=0.3)
    if name == "buzz":
        return _tone(150, 0.25, volume=0.5, wave_kind="square", decay=0.1)
    if name == "tada":
        return _stagger(
            [
                (0.0, _tone(523.25, 0.18, volume=0.5, decay=0.1)),
                (0.13, _tone(659.25, 0.18, volume=0.5, decay=0.1)),
                (0.26, _tone(783.99, 0.4, volume=0.55, decay=0.3)),
            ]
        )
    if name == "tick":
        return _tone(1760, 0.05, volume=0.4, decay=0.04)
    raise ValueError(f"unknown synth sfx: {name}")


def generate_sfx(target_dir: Path | None = None) -> Path:
    """Synthesize all built-in SFX into ``target_dir`` (public-domain wav files)."""
    out = target_dir or _sfx_path()
    out.mkdir(parents=True, exist_ok=True)
    for name in SYNTH_SFX:
        _write_wav(out / f"{name}.wav", _build(name))
    attribution = out / "ATTRIBUTION.txt"
    if not attribution.exists():
        attribution.write_text(
            "These SFX are synthesized at build time by petgen (scripts/make_voice_sfx.py).\n"
            "They are original, generated from simple oscillators, and released to the\n"
            "public domain (CC0). No third-party recordings are included.\n"
            "To use curated open-source sounds instead, drop CC0/CC-BY wav files into a\n"
            "voice-pack folder and reference the filename in that pack's `sounds` map.\n",
            encoding="utf-8",
        )
    return out


def _all_synth_sfx_exist(path: Path) -> bool:
    return all((path / f"{n}.wav").is_file() for n in SYNTH_SFX)


def ensure_sfx() -> Path:
    """Guarantee the synthesized SFX exist on disk; return their directory."""
    packaged = _sfx_path()
    if _all_synth_sfx_exist(packaged):
        return packaged
    out = data_dir() / "sfx"
    if not _all_synth_sfx_exist(out):
        generate_sfx(out)
    return out


# --- playback (best-effort; needs a real audio device at runtime) -----------


def _resolve_sfx(value: str) -> Path | None:
    """Resolve a pack's sound value: a synth key or a wav filename in _sfx."""
    sfx_dir = ensure_sfx()
    if value in SYNTH_SFX:
        candidate = sfx_dir / f"{value}.wav"
        return candidate if candidate.is_file() else None
    candidate = sfx_dir / value
    if candidate.is_file():
        return candidate
    return None


class SoundService:
    """Plays per-event SFX via QSoundEffect. Degrades silently without a device.

    Each play() creates a QSoundEffect; left unchecked that leaks one object (and
    its audio buffer) per event forever in a resident app. Finished players are
    deleted via deleteLater on playingChanged, pruned before each play(), and a
    hard pool cap drops the oldest as a last resort.
    """

    def __init__(self, max_players: int = 16) -> None:
        self._players: list = []
        self._max_players = max_players
        self._enabled = True
        self._ok = False
        try:
            from PySide6.QtMultimedia import QSoundEffect  # noqa: F401

            self._ok = True
        except Exception:
            self._ok = False

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def _prune_finished(self) -> None:
        """Delete players that are no longer playing; keep the still-playing ones."""
        alive: list = []
        for player in self._players:
            try:
                playing = bool(player.isPlaying())
            except Exception:  # noqa: BLE001 - backend may be gone
                playing = True
            if playing:
                alive.append(player)
            else:
                try:
                    player.deleteLater()
                except Exception:  # noqa: BLE001 - best effort
                    pass
        self._players = alive

    def play(self, value: str | None) -> bool:
        if not self._enabled or not value or not self._ok:
            return False
        try:
            path = _resolve_sfx(value)
            if path is None:
                return False
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect

            self._prune_finished()
            # Hard cap: drop the oldest so a burst of events (or a backend that
            # never reports playingChanged) cannot grow the pool without bound.
            while len(self._players) >= self._max_players:
                old = self._players.pop(0)
                try:
                    old.stop()
                    old.deleteLater()
                except Exception:  # noqa: BLE001 - best effort
                    pass
            player = QSoundEffect()
            player.setSource(QUrl.fromLocalFile(str(path)))
            player.setVolume(0.8)
            player.playingChanged.connect(lambda p=player: self._retire(p))
            self._players.append(player)
            player.play()
            return True
        except Exception:
            return False

    def _retire(self, player) -> None:
        """playingChanged handler: when a player stops, drop and delete it."""
        try:
            if player.isPlaying():
                return
        except Exception:  # noqa: BLE001 - backend may be gone
            pass
        if player in self._players:
            self._players.remove(player)
        try:
            player.deleteLater()
        except Exception:  # noqa: BLE001 - best effort
            pass
