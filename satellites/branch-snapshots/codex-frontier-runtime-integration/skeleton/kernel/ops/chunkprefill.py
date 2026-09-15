"""Chunked prefill — split prompt, reuse KV pages.

Cite: vLLM chunked-prefill. Mobile cap = small chunk.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]
Slot = Tuple[Row, Row]


def chunks(seq: List[Row], *, size: int = 4) -> List[List[Row]]:
    n = max(1, int(size))
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def prefill(qs: List[Row], kv: List[Slot], *, size: int = 4) -> List[Row]:
    out: List[Row] = []
    acc = list(kv)
    for ch in chunks(qs, size=size):
        for q in ch:
            o = attend(q, acc)
            acc.append((q, o))
            out.append(o)
        bump(len(ch))
    return out
