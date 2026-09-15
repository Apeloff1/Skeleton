"""Gated linear attention — FlashQLA / Gated DeltaNet family.

Cite: Qwen FlashQLA (TileLang, edge CP). No S matrix. State row only.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def gate(x: Row, g: Row) -> Row:
    out = [xi * (1.0 / (1.0 + abs(gi))) for xi, gi in zip(x, g)]
    bump(len(out))
    return out


def linattn(xs: List[Row], gs: List[Row], *, decay: float = 0.92) -> Row:
    if not xs:
        return []
    a = max(0.0, min(1.0, float(decay)))
    h = [0.0] * len(xs[0])
    for x, g in zip(xs, gs or xs):
        gx = gate(x, g)
        h = [a * hi + (1.0 - a) * vi for hi, vi in zip(h, gx)]
    bump(len(h))
    return h
