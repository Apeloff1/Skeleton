"""Sliding-window attention mask. Local band only."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump


def mask(n: int, width: int = 4) -> List[List[int]]:
    n = max(1, int(n))
    w = max(1, int(width))
    out = []
    for i in range(n):
        row = [1 if abs(i - j) <= w else 0 for j in range(n)]
        out.append(row)
    bump(n * n)
    return out
