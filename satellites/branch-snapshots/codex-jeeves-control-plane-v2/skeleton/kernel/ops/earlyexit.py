"""Early-exit / confidence halt — superfluous decoder skip.

If max-prob clears the floor, stop stacking layers.
"""
from __future__ import annotations

import math
from typing import Sequence

from skeleton.kernel.ops._stat import bump


def halt(logits: Sequence[float], *, floor: float = 0.85) -> bool:
    if not logits:
        bump(1)
        return True
    m = max(logits)
    ex = [math.exp(v - m) for v in logits]
    z = sum(ex) or 1.0
    p = max(ex) / z
    bump(1)
    return p >= max(0.0, min(1.0, float(floor)))


def remaining(depth: int, halted: bool) -> int:
    return 0 if halted else max(0, int(depth))
