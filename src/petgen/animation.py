from __future__ import annotations

import math
from collections.abc import Mapping

from petgen.pet_manifest import AnimationSpec

DEFAULT_FPS = 1.0


def frame_interval_ms(fps: float) -> int:
    """Convert an animation fps to a timer interval in milliseconds.

    Guards non-finite / non-positive fps (falls back to ``DEFAULT_FPS``) and clamps
    the result to at least 1 ms so a huge fps never yields a zero-length timer.
    """
    if fps is None or not math.isfinite(fps) or fps <= 0:
        fps = DEFAULT_FPS
    return max(1, round(1000.0 / fps))


class AnimationScheduler:
    """Pure-Python animation state machine driven tick-by-tick by the Qt layer."""

    def __init__(
        self,
        animations: Mapping[str, AnimationSpec],
        *,
        initial: str = "idle",
    ) -> None:
        if not animations:
            raise ValueError("no animations defined")
        self._animations = dict(animations)
        self._current = self._resolve(initial)
        self._pointer = 0
        self._skip_empty()

    def play(self, name: str) -> None:
        self._current = self._resolve(name)
        self._pointer = 0
        self._skip_empty()

    def advance(self) -> None:
        spec = self._animations[self._current]
        n = len(spec.frames)
        if n == 0:
            self._fallback()
            return
        self._pointer += 1
        if self._pointer < n:
            return
        if spec.loop:
            self._pointer = 0
        else:
            target = self._resolve(spec.fallback)
            if target == self._current:
                # self-fallback on a non-looping animation: loop in place instead of recursing
                self._pointer = 0
            else:
                self.play(target)

    def current_index(self) -> int:
        spec = self._animations[self._current]
        if not spec.frames:
            return 0
        return spec.frames[self._pointer]

    @property
    def current_animation(self) -> str:
        return self._current

    @property
    def current_fps(self) -> float:
        return self._animations[self._current].fps

    def animation_names(self) -> list[str]:
        return list(self._animations.keys())

    def _resolve(self, name: str) -> str:
        if name in self._animations:
            return name
        if "idle" in self._animations:
            return "idle"
        return next(iter(self._animations))

    def _skip_empty(self) -> None:
        seen: set[str] = set()
        while not self._animations[self._current].frames:
            if self._current in seen:
                return  # every reachable animation is empty; give up gracefully
            seen.add(self._current)
            self._current = self._resolve(self._animations[self._current].fallback)
            self._pointer = 0

    def _fallback(self) -> None:
        target = self._resolve(self._animations[self._current].fallback)
        if target == self._current:
            return
        self.play(target)
