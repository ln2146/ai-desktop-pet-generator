from __future__ import annotations

import math

import pytest

from petgen.animation import AnimationScheduler, frame_interval_ms
from petgen.pet_manifest import AnimationSpec


def spec(frames, *, fps=1.0, loop=True, fallback="idle") -> AnimationSpec:
    return AnimationSpec(tuple(frames), fps, loop, fallback)


def test_frame_interval_ms_common_values() -> None:
    assert frame_interval_ms(1.0) == 1000
    assert frame_interval_ms(2.0) == 500
    assert frame_interval_ms(4.0) == 250


@pytest.mark.parametrize("bad", [0, -3, float("nan"), float("inf"), None])
def test_frame_interval_ms_coerces_invalid(bad) -> None:
    assert frame_interval_ms(bad) == 1000


def test_frame_interval_ms_huge_fps_clamps_to_one() -> None:
    assert frame_interval_ms(1e9) == 1


def test_scheduler_requires_animations() -> None:
    with pytest.raises(ValueError):
        AnimationScheduler({})


def test_idle_loops_forever() -> None:
    sched = AnimationScheduler({"idle": spec([0, 1, 2], loop=True)})

    seen = [sched.current_index()]
    for _ in range(8):
        sched.advance()
        seen.append(sched.current_index())

    assert sched.current_animation == "idle"
    assert seen == [0, 1, 2, 0, 1, 2, 0, 1, 2]


def test_non_loop_falls_back_to_idle() -> None:
    sched = AnimationScheduler(
        {
            "idle": spec([0, 1], loop=True),
            "happy": spec([10, 11], loop=False, fallback="idle"),
        }
    )

    sched.play("happy")
    assert sched.current_index() == 10
    sched.advance()
    assert sched.current_index() == 11
    sched.advance()
    assert sched.current_animation == "idle"
    assert sched.current_index() == 0


def test_play_unknown_resolves_to_idle() -> None:
    sched = AnimationScheduler({"idle": spec([0, 1], loop=True)})
    sched.play("does-not-exist")
    assert sched.current_animation == "idle"


def test_self_fallback_non_loop_wraps_in_place() -> None:
    sched = AnimationScheduler({"x": spec([5], loop=False, fallback="x")})

    sched.advance()

    assert sched.current_animation == "x"
    assert sched.current_index() == 5


def test_empty_frames_falls_back_on_play() -> None:
    sched = AnimationScheduler(
        {
            "idle": spec([0], loop=True),
            "empty": spec([], loop=False, fallback="idle"),
        }
    )

    sched.play("empty")

    assert sched.current_animation == "idle"


def test_current_fps_tracks_animation() -> None:
    sched = AnimationScheduler(
        {
            "idle": spec([0], fps=1.0, loop=True),
            "happy": spec([1], fps=4.0, loop=False, fallback="idle"),
        }
    )
    assert sched.current_fps == 1.0
    sched.play("happy")
    assert sched.current_fps == 4.0
    _ = math.isfinite(sched.current_fps)
