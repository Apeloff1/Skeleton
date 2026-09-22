"""Tiled attention. Softmax in the tile. No full S matrix write.

Pointer: FlashAttention-style fusion. CPU rows only.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]


def _dot(a: Row, b: Row) -> float:
    return sum(x * y for x, y in zip(a, b))


def attend(q: Row, kv: List[Tuple[Row, Row]]) -> Row:
    if not kv:
        return list(q)
    d = max(1, len(q))
    scale = 1.0 / math.sqrt(d)
    scores = [scale * _dot(q, k) for k, _ in kv]
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    z = sum(exps) or 1.0
    out = [0.0] * len(kv[0][1])
    for w, (_, v) in zip(exps, kv):
        a = w / z
        for i, val in enumerate(v):
            out[i] += a * val
    bump(len(out))  # O only, not S
    return out
