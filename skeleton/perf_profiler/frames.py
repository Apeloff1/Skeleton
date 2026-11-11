"""Frame-time sampler: fixed-size ring buffer plus hitch detection vs budget."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional, Tuple

from ._stats import percentile_summary
from .clock import Clock, MonotonicClock


def _finite_number(value: object) -> float | None:
    """Accept only finite real builtins; reject bools and overflowing integers."""
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class Hitch:
    frame_index: int
    frame_ms: float
    budget_ms: float

    @property
    def over_ms(self) -> float:
        return self.frame_ms - self.budget_ms


@dataclass(frozen=True)
class FrameStats:
    frames: int
    window: int
    budget_ms: float
    hitch_count: int
    hitch_ratio: float
    worst_ms: float
    percentiles: Dict[str, Any]

    def within_budget(self, max_hitch_ratio: float = 0.0) -> bool:
        """Fail closed for empty windows and malformed/unsafe ratio limits."""
        limit = _finite_number(max_hitch_ratio)
        return (self.window > 0 and limit is not None
                and 0.0 <= limit <= 1.0 and self.hitch_ratio <= limit)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frames": self.frames,
            "window": self.window,
            "budget_ms": self.budget_ms,
            "hitch_count": self.hitch_count,
            "hitch_ratio": self.hitch_ratio,
            "worst_ms": self.worst_ms,
            "percentiles": self.percentiles,
        }


class FrameSampler:
    """Records frame durations into a ring buffer of the last ``capacity`` frames.

    A frame is a hitch when ``frame_ms > budget_ms * hitch_factor``. Hitches
    are kept in their own bounded ring so a long session can't grow memory.
    Use ``mark()`` once per frame (timed via the injected clock) or
    ``record(frame_ms)`` with an externally measured duration.
    """

    def __init__(
        self,
        budget_ms: float = 1000.0 / 60.0,
        capacity: int = 600,
        hitch_factor: float = 1.0,
        clock: Optional[Clock] = None,
        max_hitches: int = 256,
    ) -> None:
        budget = _finite_number(budget_ms)
        factor = _finite_number(hitch_factor)
        if budget is None or budget <= 0:
            raise ValueError("budget_ms must be a positive finite number")
        if capacity < 1 or max_hitches < 1:
            raise ValueError("capacity and max_hitches must be >= 1")
        if factor is None or factor < 1.0:
            raise ValueError("hitch_factor must be finite and >= 1.0")
        if not math.isfinite(budget * factor):
            raise ValueError("hitch threshold must be finite")
        self.budget_ms = budget
        self.hitch_factor = factor
        self.clock: Clock = clock or MonotonicClock()
        self._ring: Deque[float] = deque(maxlen=capacity)
        self._hitches: Deque[Hitch] = deque(maxlen=max_hitches)
        self._frames = 0
        self._last_mark: Optional[float] = None

    @property
    def threshold_ms(self) -> float:
        return self.budget_ms * self.hitch_factor

    def record(self, frame_ms: float) -> Optional[Hitch]:
        if isinstance(frame_ms, bool) or not isinstance(frame_ms, (int, float)) or not math.isfinite(frame_ms) or frame_ms < 0:
            raise ValueError(f"frame_ms must be a finite non-negative number, got {frame_ms!r}")
        index = self._frames
        self._frames += 1
        self._ring.append(float(frame_ms))
        if frame_ms > self.threshold_ms:
            hitch = Hitch(index, float(frame_ms), self.budget_ms)
            self._hitches.append(hitch)
            return hitch
        return None

    def mark(self) -> Optional[Hitch]:
        """Call at each frame boundary; the first call only starts timing."""
        now = self.clock.now_ms()
        previous, self._last_mark = self._last_mark, now
        if previous is None:
            return None
        return self.record(now - previous)

    def reset(self) -> None:
        self._ring.clear()
        self._hitches.clear()
        self._frames = 0
        self._last_mark = None

    @property
    def window(self) -> Tuple[float, ...]:
        return tuple(self._ring)

    @property
    def hitches(self) -> Tuple[Hitch, ...]:
        return tuple(self._hitches)

    def stats(self) -> FrameStats:
        window = list(self._ring)
        hitches_in_window = sum(1 for v in window if v > self.threshold_ms)
        return FrameStats(
            frames=self._frames,
            window=len(window),
            budget_ms=self.budget_ms,
            hitch_count=hitches_in_window,
            hitch_ratio=(hitches_in_window / len(window)) if window else 0.0,
            worst_ms=max(window, default=0.0),
            percentiles=percentile_summary("frame_ms", window) if window else {"name": "frame_ms", "samples": 0},
        )
