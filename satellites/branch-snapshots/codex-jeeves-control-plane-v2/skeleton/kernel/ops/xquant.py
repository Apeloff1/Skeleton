"""XQuant — cache layer input X, rematerialize K/V.

Cite: arXiv 2508.10395. Store X low-bit, rebuild K/V. No KV body.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.qlinear import qlinear, quantize

Row = List[float]


def pack_x(x: Row) -> Tuple[List[int], List[float]]:
    w, s = quantize([x])
    bump(len(x))
    return w[0], s


def rematerialize(x_q: List[int], s: List[float], wk: List[List[int]], sk: List[float],
                  wv: List[List[int]], sv: List[float]) -> Tuple[Row, Row]:
    x = [xi * (s[0] if s else 1.0) for xi in x_q]
    k = qlinear(x, wk, sk)
    v = qlinear(x, wv, sv)
    bump(len(k) + len(v))
    return k, v


def bytes_saved(seq: int, d: int) -> int:
    # naive 2*seq*d vs 1*seq*d
    return max(0, int(seq) * int(d))
