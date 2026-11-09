"""FP8 KV pack — scale + int8 stand-in.

Cite: vLLM Triton MLA FP8 KV, Qwen Flash NVFP4 field reports.
CPU house has no e4m3; scale*int is the law.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]


def pack(row: Row) -> Tuple[List[int], float]:
    if not row:
        return [], 1.0
    peak = max(abs(v) for v in row) or 1.0
    scale = peak / 127.0
    q = [max(-127, min(127, int(round(v / scale)))) for v in row]
    bump(len(q))
    return q, scale


def unpack(q: List[int], scale: float) -> Row:
    s = float(scale) or 1.0
    out = [v * s for v in q]
    bump(len(out))
    return out


def footprint(seq: int, d: int, *, packed: bool = True) -> int:
    return int(seq) * int(d) * (1 if packed else 2)
