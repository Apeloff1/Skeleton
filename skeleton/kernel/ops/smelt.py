"""SMELT — Sparse MoE Transformer, middle layers Loop Twice.

Cite: arXiv 2609.01343. Loop the middle half once more. Budget-matched.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def split(n: int) -> tuple:
    n = max(3, int(n))
    head = max(1, n // 4)
    mid = max(1, n // 2)
    tail = max(1, n - head - mid)
    return head, mid, tail


def smelt(x: Row, *, layers: int = 8) -> dict:
    h, m, t = split(layers)
    y = list(x)
    for _ in range(h):
        y = block(y)
    mid = list(y)
    for _ in range(m):
        y = block(y)
    # second visit of the middle half
    y = mid
    for _ in range(m):
        y = block(y)
    for _ in range(t):
        y = block(y)
    bump(len(y))
    return {
        "kind": "smelt",
        "head": h,
        "mid": m,
        "tail": t,
        "visits": 2,
        "effective": h + 2 * m + t,
        "h": y,
        "stored_prose": 0,
    }
