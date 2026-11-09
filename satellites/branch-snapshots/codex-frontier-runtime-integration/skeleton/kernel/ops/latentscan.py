"""Latent scan — compress, scan, expand."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def latentscan(x: Row, *, width: int = 2) -> Row:
    if not x:
        return []
    w = max(1, int(width))
    lat: Row = []
    for i in range(0, len(x), w):
        chunk = x[i:i + w]
        lat.append(sum(chunk) / len(chunk))
    s = 0.0
    scanned: Row = []
    for v in lat:
        s += v
        scanned.append(s)
    out: Row = []
    for i, v in enumerate(x):
        out.append(v + scanned[min(i // w, len(scanned) - 1)])
    bump(len(out))
    return out
