"""Marlin-style INT4 unpack fused into the dot.

Cite: Marlin FP16×INT4 GEMM. Unpack lives in the MAC, not a temp.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]


def pack4(w: Row) -> Tuple[List[int], float]:
    peak = max((abs(v) for v in w), default=1.0) or 1.0
    s = peak / 7.0
    q = [max(-8, min(7, int(round(v / s)))) for v in w]
    bump(len(q))
    return q, s


def dot4(x: Row, q: List[int], scale: float) -> float:
    acc = 0.0
    for xi, qi in zip(x, q):
        acc += xi * qi
    bump(1)
    return acc * float(scale)


def gemm4(x: Row, Wq: List[List[int]], scales: List[float]) -> Row:
    out = [dot4(x, row, scales[i] if i < len(scales) else 1.0) for i, row in enumerate(Wq)]
    bump(len(out))
    return out
