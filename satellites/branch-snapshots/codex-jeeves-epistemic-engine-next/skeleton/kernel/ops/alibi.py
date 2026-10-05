"""ALiBi slopes on attention scores. No extra params."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump


def slopes(n_heads: int) -> List[float]:
    n = max(1, int(n_heads))
    ratio = 2 ** (-8 / n)
    out = [ratio ** (i + 1) for i in range(n)]
    bump(n)
    return out


def bias(qlen: int, klen: int, slope: float) -> List[List[float]]:
    rows = []
    for i in range(qlen):
        rows.append([slope * (j - klen + 1) for j in range(klen)])
    bump(qlen * klen)
    return rows
