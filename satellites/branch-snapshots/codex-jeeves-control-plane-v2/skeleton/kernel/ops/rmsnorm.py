"""RMSNorm. FlashNorm handle: scale can merge into the next linear."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def rmsnorm(x: Row, g: Row | None = None, *, eps: float = 1e-6) -> Row:
    n = len(x)
    if n == 0:
        return []
    mean_sq = sum(v * v for v in x) / n
    inv = 1.0 / math.sqrt(mean_sq + eps)
    if g is None:
        out = [v * inv for v in x]
    else:
        out = [v * inv * g[i] for i, v in enumerate(x)]
    bump(n)
    return out


def merge_gain(w: List[Row], g: Row) -> List[Row]:
    """FlashNorm merge: W*[i,j] = g[j] * W[i,j]. One write of W*."""
    out = [[g[j] * row[j] for j in range(len(row))] for row in w]
    bump(sum(len(r) for r in out))
    return out
