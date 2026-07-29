from __future__ import annotations

from petgen.idle_time import get_idle_seconds


def test_get_idle_seconds_never_raises() -> None:
    """The probe must be safe to call anywhere -- it degrades to None, never raises."""
    value = get_idle_seconds()
    assert value is None or value >= 0


def test_get_idle_seconds_is_float_or_none() -> None:
    value = get_idle_seconds()
    assert value is None or isinstance(value, float)
