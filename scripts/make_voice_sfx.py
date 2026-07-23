#!/usr/bin/env python3
"""Synthesize the built-in (public-domain) SFX wav files.

These sounds are generated from simple oscillators at build/install time, so the
repo ships no third-party recordings. Run manually to (re)generate, or let the
app call ``petgen.sound.ensure_sfx()`` on first launch.

    python scripts/make_voice_sfx.py [target_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from petgen.sound import generate_sfx  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else None
    out = generate_sfx(target)
    print(f"wrote synthesized SFX to {out}")
    for wav in sorted(out.glob("*.wav")):
        print(f"  {wav.name} ({wav.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
