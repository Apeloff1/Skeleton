"""Parallel Loop Transformer — stagger loop index across tokens.

Cite: PLT arXiv 2510.24824. Token t at loop r, token t-1 at loop r+1.
Non-first loops use a short window.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block
from skeleton.kernel.ops.window import mask

Row = List[float]


def plt(xs: List[Row], *, r: int = 2) -> dict:
    r = max(1, min(4, int(r)))
    states = [list(x) for x in xs]
    for step in range(r):
        nxt = []
        win = 2 if step else len(states)
        for i, h in enumerate(states):
            # later tokens see earlier tokens further along the loop
            src = states[max(0, i - win) : i + 1]
            y = block(h, [(s, s) for s in src] or None)
            nxt.append(y)
        states = nxt
        bump(len(states))
    return {
        "kind": "plt",
        "r": r,
        "n": len(states),
        "window": 2,
        "h": states,
        "stored_prose": 0,
    }


def swa_ok(n: int) -> List[List[int]]:
    return mask(n, 2)
