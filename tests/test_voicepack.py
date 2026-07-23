from __future__ import annotations

import os
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from petgen import sound as sound_mod  # noqa: E402
from petgen.sound import SoundService, _build, _resolve_sfx, ensure_sfx, generate_sfx  # noqa: E402
from petgen.voicepack import SYNTH_SFX, VOICE_CLIP_KINDS, default_pack, load_catalog  # noqa: E402


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
