"""Ponder / ACT halt score — adaptive compute per row.

Cite: Adaptive Computation Time on the looped stack.
"""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.earlyexit import halt
from skeleton.kernel.ops.loop import block

Row = List[float]


def ponder(x: Row) -> float:
    if not x:
        return 1.0
    m = max(x)
    ex = [math.exp(v - m) for v in x]
    z = sum(ex) or 1.0
    p = max(ex) / z
    bump(1)
    return p


def act(x: Row, *, floor: float = 0.8, r_max: int = 4) -> dict:
    h = list(x)
    used = 0
    for i in range(max(1, int(r_max))):
        h = block(h)
        used = i + 1
        if halt(h, floor=floor) or ponder(h) >= floor:
            break
    bump(len(h))
    return {
        "kind": "ponder-act",
        "used": used,
        "score": ponder(h),
        "h": h,
        "stored_prose": 0,
    }
