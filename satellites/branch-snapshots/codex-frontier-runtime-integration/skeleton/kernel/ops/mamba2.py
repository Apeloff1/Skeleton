"""Mamba-2 style diagonal scan — cheap state mix."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def mamba2(x: Row, a: Row, b: Row) -> Row:
    n = min(len(x), len(a), len(b))
    h = 0.0
    out: Row = []
    for i in range(n):
        h = a[i] * h + b[i] * x[i]
        out.append(h)
    bump(n)
    return out
