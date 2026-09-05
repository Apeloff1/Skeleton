"""KV share across loops — Huginn-style cache reuse.

First pass writes KV. Later passes read it. No second write.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend
from skeleton.kernel.ops.rmsnorm import rmsnorm

Row = List[float]
Slot = Tuple[Row, Row]


def first(x: Row) -> Tuple[Row, List[Slot]]:
    h = rmsnorm(x)
    kv = [(h, h)]
    o = attend(h, kv)
    bump(len(o))
    return o, kv


def again(x: Row, kv: List[Slot]) -> Row:
    h = rmsnorm(x)
    o = attend(h, kv)
    bump(len(o))
    return o


def share(x: Row, *, r: int = 2) -> dict:
    y, kv = first(x)
    for _ in range(max(0, int(r) - 1)):
        y = again(y, kv)
    bump(len(y))
    return {
        "kind": "kv-share",
        "r": max(1, int(r)),
        "kv_n": len(kv),
        "rewrites": 0,
        "h": y,
        "stored_prose": 0,
    }
