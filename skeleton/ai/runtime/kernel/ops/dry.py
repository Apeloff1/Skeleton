"""DRY / presence penalty — obscure anti-repeat.

Subtract mass from recently emitted tokens. No RNG.
"""
from __future__ import annotations

from typing import List, Sequence

from skeleton.kernel.ops._stat import bump


def presence(logits: Sequence[float], seen: Sequence[int], *, pen: float = 0.6) -> List[float]:
    out = list(logits)
    p = max(0.0, float(pen))
    for i in seen:
        if 0 <= i < len(out):
            out[i] -= p
    bump(len(out))
    return out


def dry(logits: Sequence[float], recent: Sequence[int], *, mul: float = 0.5) -> List[float]:
    out = list(logits)
    m = max(0.0, min(1.0, float(mul)))
    for i in recent:
        if 0 <= i < len(out):
            out[i] *= m
    bump(len(out))
    return out
