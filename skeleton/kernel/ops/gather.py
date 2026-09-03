"""Gather / scatter over paged KV rows."""
from __future__ import annotations

from typing import List, Sequence, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]


def gather(pages: Sequence[Tuple[Row, Row]], idx: Sequence[int]) -> List[Tuple[Row, Row]]:
    out = []
    for i in idx:
        if 0 <= i < len(pages):
            k, v = pages[i]
            out.append((list(k), list(v)))
    bump(len(out))
    return out


def scatter(pages: List[Tuple[Row, Row]], idx: int, kv: Tuple[Row, Row]) -> None:
    if 0 <= idx < len(pages):
        pages[idx] = (list(kv[0]), list(kv[1]))
        bump(1)
