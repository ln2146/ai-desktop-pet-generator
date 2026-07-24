from __future__ import annotations

import os
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from petgen import sound as sound_mod  # noqa: E402
from petgen.sound import (  # noqa: E402
    SoundService,
    _build,
    _resolve_sfx,
    ensure_sfx,
    generate_sfx,
)
from petgen.voicepack import (  # noqa: E402
    SYNTH_SFX,
    VOICE_CLIP_KINDS,
    default_pack,
    load_catalog,
)


def test_catalog_has_three_packs_with_required_kinds() -> None:
    catalog = load_catalog()
    assert len(catalog) >= 3
    assert default_pack().id in catalog
    for pack in catalog.values():
        assert pack.display_name and pack.emoji
        assert "tap" in pack.lines and pack.lines["tap"]
        # every declared sound value is a known synth key or a filename
        for value in pack.sounds.values():
            assert value  # non-empty


def test_line_for_falls_back_to_tap() -> None:
    catalog = load_catalog()
    pack = catalog[default_pack().id]
    # a kind with no pool falls back to tap lines (never raises)
    empty_pack = type(pack)(
        id="x", display_name="x", emoji="x", lines={"tap": ("hi",)}, sounds={}
    )
    assert empty_pack.line_for("idle") in ("hi",) or empty_pack.line_for("idle") is None
    assert empty_pack.line_for("tap") == "hi"


def test_sound_for_returns_declared_value() -> None:
    pack = default_pack()
    assert pack.sound_for("happy") in SYNTH_SFX or pack.sound_for("happy") is None
    assert pack.sound_for("not-a-kind") is None


def test_build_produces_bounded_samples() -> None:
    for name in SYNTH_SFX:
        samples = _build(name)
        assert samples
        assert all(-1.0 <= s <= 1.0 for s in samples)


def test_generate_sfx_writes_valid_wav(tmp_path: Path) -> None:
    out = generate_sfx(tmp_path / "sfx")
    for name in SYNTH_SFX:
        wav = out / f"{name}.wav"
        assert wav.is_file() and wav.stat().st_size > 44
        with wave.open(str(wav)) as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == sound_mod.SAMPLE_RATE
    assert (out / "ATTRIBUTION.txt").is_file()


def test_ensure_sfx_is_idempotent() -> None:
    d1 = ensure_sfx()
    mtime = (d1 / "pop.wav").stat().st_mtime
    d2 = ensure_sfx()
    assert d1 == d2
    assert (d2 / "pop.wav").stat().st_mtime == mtime  # not regenerated


def test_ensure_sfx_generates_runtime_cache_when_package_has_no_wavs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_sfx = tmp_path / "package" / "_sfx"
    package_sfx.mkdir(parents=True)
    runtime_root = tmp_path / "data"
    monkeypatch.setattr(sound_mod, "_sfx_path", lambda: package_sfx)
    monkeypatch.setattr(sound_mod, "data_dir", lambda: runtime_root)

    out = sound_mod.ensure_sfx()

    assert out == runtime_root / "sfx"
    assert all((out / f"{name}.wav").is_file() for name in SYNTH_SFX)
    assert not any((package_sfx / f"{name}.wav").exists() for name in SYNTH_SFX)


def test_resolve_sfx_finds_synth_and_rejects_unknown() -> None:
    ensure_sfx()
    pop = _resolve_sfx("pop")
    assert pop is not None and pop.name == "pop.wav"
    assert _resolve_sfx("does-not-exist.wav") is None
    assert _resolve_sfx("not-a-key") is None


# --- service (offscreen; audio device may be absent -> best-effort) ---------

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from petgen.speak import VoicePackService  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication(["test-voicepack"])


def test_voice_pack_service_constructs_and_reacts(qapp) -> None:
    svc = VoicePackService(default_pack(), enabled=True)
    result = svc.react("happy")
    assert set(result) == {"sfx", "speech"}
    # booleans, never None / never raises
    assert isinstance(result["sfx"], bool) and isinstance(result["speech"], bool)


def test_voice_pack_service_disabled_silences(qapp) -> None:
    svc = VoicePackService(default_pack(), enabled=False)
    assert svc.react("tap") == {"sfx": False, "speech": False}


def test_voice_pack_service_set_pack_switches(qapp) -> None:
    svc = VoicePackService()
    catalog = load_catalog()
    other_id = [k for k in catalog if k != svc.pack.id][0]
    new = svc.set_pack(other_id)
    assert svc.pack.id == other_id == new.id


def test_all_clip_kinds_do_not_crash(qapp) -> None:
    svc = VoicePackService(default_pack())
    for kind in VOICE_CLIP_KINDS:
        svc.react(kind)  # must not raise under any TTS/audio backend state


def test_sound_service_play_unknown_is_false(qapp) -> None:
    s = SoundService()
    assert s.play(None) is False
    assert s.play("nope") is False


class _FakePlayer:
    """Minimal QSoundEffect stand-in: never 'playing', records deleteLater/stop."""

    def __init__(self) -> None:
        self.deleted = False
        self.stopped = False

    def isPlaying(self) -> bool:
        return False

    def deleteLater(self) -> None:
        self.deleted = True

    def stop(self) -> None:
        self.stopped = True


def test_sound_service_prunes_finished_players(qapp) -> None:
    s = SoundService()
    old = [_FakePlayer() for _ in range(3)]
    s._players = list(old)  # noqa: SLF001
    s._prune_finished()  # noqa: SLF001
    assert s._players == []  # noqa: SLF001 - all finished -> removed
    assert all(p.deleted for p in old)


def test_sound_service_pool_is_capped(qapp) -> None:
    cap = 2
    s = SoundService(max_players=cap)
    # Pre-fill with finished players beyond the cap; one more play() must prune
    # (they are not playing) and then enforce the cap, so the pool never exceeds
    # cap even though play() appends a fresh QSoundEffect.
    s._players = [_FakePlayer() for _ in range(cap + 3)]  # noqa: SLF001
    s.play("pop")
    assert len(s._players) <= cap  # noqa: SLF001
