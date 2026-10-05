"""QK-Norm — per-head RMS on Q and K before the tile.

Obscure Gemma/PaLM-2 path. Stops logit blow-up without touching V.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.rmsnorm import rmsnorm

Row = List[float]


def qk_norm(q: Row, k: Row, *, eps: float = 1e-6) -> Tuple[Row, Row]:
    qn = rmsnorm(q)
    kn = rmsnorm(k)
    bump(len(qn) + len(kn))
    return qn, kn


def qk_clip(q: Row, *, cap: float = 10.0) -> Row:
    c = max(1e-6, float(cap))
    out = [max(-c, min(c, v)) for v in q]
    bump(len(out))
    return out
