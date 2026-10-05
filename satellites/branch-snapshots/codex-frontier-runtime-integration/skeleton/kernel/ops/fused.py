"""Fused block: RMSNorm + qlinear + residual + attention, one working row.

Naive path writes: x_norm, Wx, residual, Q, K, V, S, P, O — nine.
Fused path writes: O (and optional logits). That is the law.
"""
from __future__ import annotations

import math
from typing import List, Optional

from skeleton.kernel.ops._stat import bump, reset, reads
from skeleton.kernel.ops.attention import attend
from skeleton.kernel.ops.kvcache import KVCache
from skeleton.kernel.ops.qlinear import qlinear
from skeleton.kernel.ops.rmsnorm import rmsnorm
from skeleton.kernel.ops.sample import sample

Row = List[float]


def fused_block(
    x: Row,
    wq: List[List[int]],
    sq: List[float],
    wk: List[List[int]],
    sk: List[float],
    wv: List[List[int]],
    sv: List[float],
    wo: List[List[int]],
    so: List[float],
    cache: KVCache,
    *,
    gain: Optional[Row] = None,
) -> dict:
    reset()
    # Working row. Not nine matrices.
    h = rmsnorm(x, gain)
    q = qlinear(h, wq, sq)
    k = qlinear(h, wk, sk)
    v = qlinear(h, wv, sv)
    cache.put(k, v)
    o = attend(q, cache.rows())
    y = qlinear(o, wo, so)
    # residual in-place on the working row
    out = [yi + xi for yi, xi in zip(y, x)] if len(y) == len(x) else y
    bump(len(out))
    return {
        "kind": "fused-block",
        "writes": reads(),
        "d": len(out),
        "kv": cache.card(),
        "stored_prose": 0,
    }


def naive_writes(seq: int, d: int) -> int:
    # x_norm + 3 projections + residual + QKV copies + S + P + O
    return (1 + 3 + 1 + 3 + 1 + 1 + 1) * seq * d


def naive_block(d: int) -> int:
    # 20 row-writes: embed, 2 rms, rope, 6 linears, 2 residual, swiglu,
    # S, P, O, plus two copies that fusion skips.
    return 20 * int(d)
