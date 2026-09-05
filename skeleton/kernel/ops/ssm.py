"""Tiny SSM scan — Mamba/S4-ish sequential mix.

Superfluous next to attention. One state row, no S matrix.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def scan(xs: List[Row], *, decay: float = 0.9) -> Row:
    if not xs:
        return []
    a = max(0.0, min(1.0, float(decay)))
    h = [0.0] * len(xs[0])
    for row in xs:
        h = [a * hi + (1.0 - a) * xi for hi, xi in zip(h, row)]
    bump(len(h))
    return h


def step(h: Row, x: Row, *, decay: float = 0.9) -> Row:
    a = max(0.0, min(1.0, float(decay)))
    out = [a * hi + (1.0 - a) * xi for hi, xi in zip(h, x)]
    bump(len(out))
    return out
