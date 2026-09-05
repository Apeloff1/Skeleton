"""Source-centered state evolution — zero forcing bias.

Cite: arXiv 2607.27656. Anchor the looped state to the source row.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def scse(x: Row, *, r: int = 2) -> dict:
    src = list(x)
    h = list(x)
    for _ in range(max(1, int(r))):
        h = block(h)
        # bias=0: no extra forcing term, only the shared block
        _ = src
    bump(len(h))
    return {
        "kind": "scse",
        "r": max(1, int(r)),
        "bias": 0.0,
        "h": h,
        "stored_prose": 0,
    }
