"""Latent orbit — Huginn-style cyclic state on numeric rows.

If the row starts repeating a cycle, mark deliberation, not progress.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def _sig(x: Row) -> tuple:
    return tuple(round(v, 3) for v in x)


def orbit(x: Row, *, r: int = 6) -> dict:
    h = list(x)
    seen = {_sig(h): 0}
    cyc = 0
    used = 0
    for i in range(max(1, int(r))):
        h = block(h)
        used = i + 1
        s = _sig(h)
        if s in seen:
            cyc = used - seen[s]
            break
        seen[s] = used
    bump(len(h))
    return {
        "kind": "orbit",
        "used": used,
        "cycle": cyc,
        "deliberation": int(cyc > 0),
        "h": h,
        "stored_prose": 0,
    }
