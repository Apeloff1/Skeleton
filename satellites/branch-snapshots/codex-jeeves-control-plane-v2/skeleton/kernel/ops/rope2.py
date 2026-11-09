"""Two-axis RoPE — rotate even/odd pairs on two frequencies."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def rope2(x: Row, *, pos: int = 1, base: float = 10000.0) -> Row:
    out = list(x)
    for i in range(0, len(out) - 1, 2):
        theta = pos / (base ** (i / max(len(out), 2)))
        c, s = math.cos(theta), math.sin(theta)
        a, b = out[i], out[i + 1]
        out[i] = a * c - b * s
        out[i + 1] = a * s + b * c
    bump(len(out))
    return out
