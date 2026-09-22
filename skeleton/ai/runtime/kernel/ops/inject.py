"""Input injection — add the embed back each loop.

Stops hidden drift off the distribution later layers expect.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def inject(h: Row, src: Row, *, gain: float = 0.3) -> Row:
    g = max(0.0, float(gain))
    out = [hi + g * si for hi, si in zip(h, src)]
    bump(len(out))
    return out


def loop_inject(x: Row, *, r: int = 2, gain: float = 0.3) -> dict:
    h = list(x)
    for _ in range(max(1, int(r))):
        h = block(h)
        h = inject(h, x, gain=gain)
    bump(len(h))
    return {
        "kind": "loop-inject",
        "r": max(1, int(r)),
        "gain": gain,
        "h": h,
        "stored_prose": 0,
    }
