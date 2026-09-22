"""Residual add. In-place on the working row."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump


def residual(x: List[float], y: List[float]) -> List[float]:
    n = min(len(x), len(y))
    out = [x[i] + y[i] for i in range(n)]
    bump(n)
    return out
