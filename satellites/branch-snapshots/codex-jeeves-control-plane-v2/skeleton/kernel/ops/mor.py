"""Mixture-of-Recursions — token-level depth router.

Cite: MoR / Mixture-of-recursions. Easy tokens R=1, hard tokens R=2+.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import unroll

Row = List[float]


def difficulty(x: Row) -> float:
    if not x:
        return 0.0
    m = sum(abs(v) for v in x) / len(x)
    return min(1.0, m)


def route_r(x: Row, *, cap: int = 4) -> int:
    d = difficulty(x)
    if d < 0.15:
        r = 1
    elif d < 0.4:
        r = 2
    else:
        r = min(int(cap), 2 + int(d * 2))
    bump(1)
    return max(1, r)


def mor(xs: List[Row], *, cap: int = 3) -> dict:
    depths = [route_r(x, cap=cap) for x in xs]
    outs = [unroll(x, r=r)["h"] for x, r in zip(xs, depths)]
    bump(len(outs))
    return {
        "kind": "mor",
        "depths": depths,
        "mean_r": (sum(depths) / len(depths)) if depths else 0,
        "outs": outs,
        "stored_prose": 0,
    }
