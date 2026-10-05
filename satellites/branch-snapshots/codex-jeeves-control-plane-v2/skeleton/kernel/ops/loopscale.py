"""Per-loop residual scale — shrink the update on later passes.

Stops the second visit from overwriting the first.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def scaled(x: Row, *, r: int = 2) -> dict:
    h = list(x)
    for i in range(max(1, int(r))):
        nxt = block(h)
        a = 1.0 / (i + 1)
        h = [a * n + (1.0 - a) * o for n, o in zip(nxt, h)]
    bump(len(h))
    return {
        "kind": "loop-scale",
        "r": max(1, int(r)),
        "h": h,
        "stored_prose": 0,
    }
