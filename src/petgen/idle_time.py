"""System idle detection, used to tell "really at the computer" from "away".

Returns seconds since the last keyboard/mouse input. Core logic is Qt-free and
adds no new dependency -- only ``ctypes`` against the OS APIs:

* macOS: ``CGEventSourceSecondsSinceLastEventType`` (CoreGraphics).
* Windows: ``GetLastInputInfo`` + ``GetTickCount`` (user32).
* other platforms / any failure: ``None`` so the caller can fall back to a
  pure elapsed-time estimate (degraded but still functional).

Every entry point is wrapped so it NEVER raises -- a misbehaving host (headless
CI, locked-down permissions, missing framework) simply degrades to ``None``.
"""

from __future__ import annotations

import sys

# --- macOS: CoreGraphics event source ----------------------------------------
# kCGEventSourceStateHIDSystemState = 1, kCGAnyInputEventType = ~0
_MAC_STATE = 1
_MAC_ANY_EVENT = 0xFFFFFFFF


def _idle_seconds_macos() -> float | None:
    try:
        import ctypes
        from ctypes import c_double, c_uint

        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGEventSourceSecondsSinceLastEventType.restype = c_double
        cg.CGEventSourceSecondsSinceLastEventType.argtypes = [c_uint, c_uint]
        secs = cg.CGEventSourceSecondsSinceLastEventType(_MAC_STATE, _MAC_ANY_EVENT)
        if secs < 0:  # error sentinel returned by the framework
            return None
        return float(secs)
    except Exception:
        return None


# --- Windows: GetLastInputInfo -----------------------------------------------


def _idle_seconds_windows() -> float | None:
    try:
        import ctypes

        class _LASTINPUTINFO(ctypes.Structure):  # noqa: N801 - mirrors Win32 naming
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        lii = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
        if not user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        now_ms = user32.GetTickCount()
        # GetTickCount wraps at 2^32 ms (~49 days); the subtraction is correct
        # as long as the value hasn't wrapped between the two calls, which is
        # astronomically unlikely in practice.
        idle_ms = (now_ms - lii.dwTime) & 0xFFFFFFFF
        return float(idle_ms) / 1000.0
    except Exception:
        return None


def get_idle_seconds() -> float | None:
    """Seconds since the last keyboard/mouse input, or ``None`` if unknown.

    Never raises; an unsupported/unavailable host returns ``None`` so callers
    can fall back to a wall-clock estimate.
    """
    if sys.platform == "darwin":
        return _idle_seconds_macos()
    if sys.platform.startswith("win"):
        return _idle_seconds_windows()
    return None
