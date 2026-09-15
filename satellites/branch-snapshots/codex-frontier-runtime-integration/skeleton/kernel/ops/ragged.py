"""Ragged attention — embeddings path, no KV page table.

Cite: Perplexity ROSE. Skip paged KV. Variable row lengths.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]


def pad(rows: List[Row]) -> List[Row]:
    if not rows:
        return []
    w = max(len(r) for r in rows)
    out = [list(r) + [0.0] * (w - len(r)) for r in rows]
    bump(sum(len(r) for r in out))
    return out


def ragged(q: Row, keys: List[Row], vals: List[Row]) -> Row:
    kv = list(zip(pad(keys), pad(vals)))
    out = attend(q if q else [0.0], kv) if kv else list(q)
    bump(len(out))
    return out
