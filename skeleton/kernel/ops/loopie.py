"""Loopie — sparse later loops. Even tokens skip pass 2+."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def loopie(xs: List[Row], *, r: int = 2) -> dict:
    states = [list(x) for x in xs]
    for step in range(max(1, int(r))):
        nxt = []
        for i, h in enumerate(states):
            if step > 0 and i % 2 == 0:
                nxt.append(h)
            else:
                nxt.append(block(h))
        states = nxt
        bump(len(states))
    return {
        "kind": "loopie",
        "r": max(1, int(r)),
        "n": len(states),
        "sparse": 1,
        "h": states,
        "stored_prose": 0,
    }
