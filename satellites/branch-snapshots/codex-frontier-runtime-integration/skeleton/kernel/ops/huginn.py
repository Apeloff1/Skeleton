"""Huginn-style inference unroll — extra R on the shared core, KV shared."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.kvshare import share
from skeleton.kernel.ops.overthink import should_stop
from skeleton.kernel.ops.loop import block

Row = List[float]


def huginn(x: Row, *, r: int = 4) -> dict:
    first = share(x, r=1)
    h = list(first.get("h") or x)
    used = 1
    for i in range(1, max(1, int(r))):
        nxt = block(h)
        used = i + 1
        if i >= 1 and should_stop(h, nxt):
            h = nxt
            break
        h = nxt
    bump(len(h))
    return {
        "kind": "huginn",
        "used": used,
        "r_max": max(1, int(r)),
        "kv_share": 1,
        "h": h,
        "stored_prose": 0,
    }
