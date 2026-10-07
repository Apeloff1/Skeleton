"""Overthink halt — extra loops that stop moving the row are waste.

Cite: Loop, Think, & Generalize arXiv 2604.07822. Excess R degrades.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def delta(a: Row, b: Row) -> float:
    if not a:
        return 0.0
    return sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)


def should_stop(prev: Row, cur: Row, *, eps: float = 1e-4) -> bool:
    bump(1)
    return delta(prev, cur) < max(0.0, float(eps))


def run(x: Row, *, r_max: int = 6, eps: float = 1e-4) -> dict:
    h = list(x)
    used = 0
    for i in range(max(1, int(r_max))):
        nxt = block(h)
        used = i + 1
        if should_stop(h, nxt, eps=eps) and i >= 1:
            h = nxt
            break
        h = nxt
    bump(len(h))
    return {
        "kind": "overthink",
        "used": used,
        "r_max": r_max,
        "halted": used < r_max,
        "h": h,
        "stored_prose": 0,
    }
