"""Layer-loop vs stack-loop.

Field: looping each layer a few times scaled better than looping the whole stack.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def layerloop(x: Row, *, layers: int = 3, inner: int = 2) -> dict:
    h = list(x)
    for _ in range(max(1, int(layers))):
        for _ in range(max(1, int(inner))):
            h = block(h)
    bump(len(h))
    return {
        "kind": "layer-loop",
        "layers": max(1, int(layers)),
        "inner": max(1, int(inner)),
        "effective": max(1, int(layers)) * max(1, int(inner)),
        "h": h,
        "stored_prose": 0,
    }


def stackloop(x: Row, *, layers: int = 3, r: int = 2) -> dict:
    h = list(x)
    for _ in range(max(1, int(r))):
        for _ in range(max(1, int(layers))):
            h = block(h)
    bump(len(h))
    return {
        "kind": "stack-loop",
        "layers": max(1, int(layers)),
        "r": max(1, int(r)),
        "effective": max(1, int(layers)) * max(1, int(r)),
        "h": h,
        "stored_prose": 0,
    }
