"""Cascade attention — coarse then fine.

Cite: long-context cascade. Cheap pass picks a window, fine attend.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]
Slot = Tuple[Row, Row]


def coarse(q: Row, kv: List[Slot], *, win: int = 2) -> List[Slot]:
    if not kv:
        return []
    w = max(1, int(win))
    scored = sorted(kv, key=lambda sl: sum(a * b for a, b in zip(q, sl[0])), reverse=True)
    bump(len(scored[:w]))
    return scored[:w]


def cascade(q: Row, kv: List[Slot], *, win: int = 2) -> Row:
    out = attend(q, coarse(q, kv, win=win))
    bump(len(out))
    return out
