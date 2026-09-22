"""MoDr — Mixture-of-Depth-Recurrent. Branch the loop, not the width.

Cite: MoDr LoRA-style branches on a Huginn backbone. House path: two cheap branches.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def _mix(a: Row, b: Row, w: float) -> Row:
    return [w * x + (1.0 - w) * y for x, y in zip(a, b)]


def modr(x: Row, *, branches: int = 2) -> dict:
    h = list(x)
    outs = []
    n = max(1, min(4, int(branches)))
    for i in range(n):
        y = list(h)
        y = block(y)
        if i:
            y = block(y)
        outs.append(y)
    w = 1.0 / n
    acc = [0.0] * len(h)
    for o in outs:
        acc = [a + w * b for a, b in zip(acc, o)]
    bump(len(acc))
    return {
        "kind": "modr",
        "branches": n,
        "h": acc,
        "stored_prose": 0,
    }
