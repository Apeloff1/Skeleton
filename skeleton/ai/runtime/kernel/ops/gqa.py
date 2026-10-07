"""Grouped-query attention — share KV across Q heads.

Cite: GQA production default in Llama/Qwen decode.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]
Slot = Tuple[Row, Row]


def group(heads_q: List[Row], kv: List[Slot], *, kv_heads: int = 1) -> List[Row]:
    if not heads_q:
        return []
    kh = max(1, int(kv_heads))
    out = []
    for i, q in enumerate(heads_q):
        # all heads share the same tiny KV in the house path
        out.append(attend(q, kv))
    bump(len(out) * (len(out[0]) if out and out[0] else 0))
    return out


def kv_ratio(q_heads: int, kv_heads: int) -> float:
    return float(max(1, q_heads)) / float(max(1, kv_heads))
