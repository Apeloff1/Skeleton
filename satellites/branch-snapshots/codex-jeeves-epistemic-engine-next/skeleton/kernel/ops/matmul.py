"""Tiled MatMul. Tile width from the tile kernel when present."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]
Mat = List[Row]


def matmul(a: Mat, b: Mat, *, tile: int = 8) -> Mat:
    n = len(a)
    k = len(a[0]) if a else 0
    m = len(b[0]) if b else 0
    tile = max(1, int(tile))
    out: Mat = [[0.0] * m for _ in range(n)]
    for i0 in range(0, n, tile):
        for j0 in range(0, m, tile):
            for p0 in range(0, k, tile):
                i1 = min(i0 + tile, n)
                j1 = min(j0 + tile, m)
                p1 = min(p0 + tile, k)
                for i in range(i0, i1):
                    ai = a[i]
                    oi = out[i]
                    for p in range(p0, p1):
                        ap = ai[p]
                        bp = b[p]
                        for j in range(j0, j1):
                            oi[j] += ap * bp[j]
    bump(n * m)
    return out
