"""Fuse scale + inject into one working row. One write."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.inject import inject
from skeleton.kernel.ops.loop import block

Row = List[float]


def loopfuse(x: Row, *, r: int = 2) -> dict:
    src = list(x)
    h = list(x)
    for i in range(max(1, int(r))):
        nxt = block(h)
        a = 1.0 / (i + 1)
        h = [a * n + (1.0 - a) * o for n, o in zip(nxt, h)]
        h = inject(h, src, gain=0.2)
    bump(len(h))
    return {
        "kind": "loop-fuse",
        "r": max(1, int(r)),
        "h": h,
        "stored_prose": 0,
    }
