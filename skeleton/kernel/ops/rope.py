"""Rotary position embedding. Even/odd pair rotate."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump


def rope(x: List[float], pos: int = 0, *, base: float = 10000.0) -> List[float]:
    n = len(x) - len(x) % 2
    out = list(x)
    for i in range(0, n, 2):
        theta = pos / (base ** (i / max(2, n)))
        c, s = math.cos(theta), math.sin(theta)
        a, b = x[i], x[i + 1]
        out[i] = a * c - b * s
        out[i + 1] = a * s + b * c
    bump(n)
    return out
