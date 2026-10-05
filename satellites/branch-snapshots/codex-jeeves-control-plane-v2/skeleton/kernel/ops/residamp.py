"""Residual damper — later loops get a smaller add."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block
from skeleton.kernel.ops.residual import residual

Row = List[float]


def residamp(x: Row, *, r: int = 3) -> dict:
    h = list(x)
    for i in range(max(1, int(r))):
        nxt = block(h)
        g = 1.0 / (1 + i)
        step = [(a - b) * g for a, b in zip(nxt, h)]
        h = residual(h, step)
    bump(len(h))
    return {
        "kind": "resi-damp",
        "r": max(1, int(r)),
        "h": h,
        "stored_prose": 0,
    }
