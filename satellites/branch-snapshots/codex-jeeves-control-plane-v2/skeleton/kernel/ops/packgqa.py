"""PackGQA — pack query heads that share one KV head.

Cite: FA3/4 PackGQA memory access. House path concatenates Q rows.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def pack(heads: List[Row], *, kv_heads: int = 1) -> List[List[Row]]:
    if not heads:
        return []
    g = max(1, int(len(heads) / max(1, kv_heads)))
    out = [heads[i : i + g] for i in range(0, len(heads), g)]
    bump(len(heads))
    return out


def unpack(groups: List[List[Row]]) -> List[Row]:
    out: List[Row] = []
    for g in groups:
        out.extend(g)
    bump(len(out))
    return out
