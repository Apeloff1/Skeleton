"""LoopFormer shortcut modulation — skip some unrolls by a scale.

Cite: LoopFormer elastic-depth. Shortcut consistency across R budgets.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def shortcut(x: Row, *, r: int = 4, skip: int = 2, scale: float = 0.5) -> dict:
    h = list(x)
    used = 0
    s = max(0.0, float(scale))
    skip_at = max(1, int(skip))
    for i in range(max(1, int(r))):
        nxt = block(h)
        if (i + 1) == skip_at:
            h = [s * a + (1.0 - s) * b for a, b in zip(h, nxt)]
        else:
            h = nxt
        used += 1
    bump(len(h))
    return {
        "kind": "shortcut",
        "r": used,
        "skip": skip_at,
        "scale": s,
        "h": h,
        "stored_prose": 0,
    }
