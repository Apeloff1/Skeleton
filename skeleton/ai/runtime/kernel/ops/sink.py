"""Attention sink — keep the first KV slot alive.

StreamingLLM / window+sink. Obscure, cheap, stops long-context rot.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]
Slot = Tuple[Row, Row]


def with_sink(kv: List[Slot], *, window: int = 4) -> List[Slot]:
    if not kv:
        return []
    w = max(1, int(window))
    if len(kv) <= w + 1:
        bump(len(kv))
        return list(kv)
    out = [kv[0], *kv[-w:]]
    bump(len(out))
    return out


def sink_pos(n: int) -> List[int]:
    if n <= 0:
        return []
    return [0] + list(range(1, n))
