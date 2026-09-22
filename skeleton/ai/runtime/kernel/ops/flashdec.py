"""Flash-decoding split-k — long-KV decode path.

Cite: Flash Decoding / FA4 split. Partial softmax per shard, merge.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]
Slot = Tuple[Row, Row]


def _shards(kv: List[Slot], k: int) -> List[List[Slot]]:
    k = max(1, min(int(k), max(1, len(kv))))
    if not kv:
        return []
    n = math.ceil(len(kv) / k)
    return [kv[i : i + n] for i in range(0, len(kv), n)]


def flashdec(q: Row, kv: List[Slot], *, splits: int = 2) -> Row:
    parts = _shards(kv, splits)
    if not parts:
        return list(q)
    acc = attend(q, parts[0])
    for shard in parts[1:]:
        nxt = attend(q, shard)
        acc = [(a + b) * 0.5 for a, b in zip(acc, nxt)]
    bump(len(acc))
    return acc
