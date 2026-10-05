"""Quantized linear. INT8 weights, row scale. FireQ handle only."""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]
Mat = List[Row]


def quantize(w: Mat) -> Tuple[List[List[int]], List[float]]:
    qw: List[List[int]] = []
    scales: List[float] = []
    for row in w:
        peak = max((abs(v) for v in row), default=1.0) or 1.0
        s = peak / 127.0
        scales.append(s)
        qw.append([max(-127, min(127, int(round(v / s)))) for v in row])
    bump(sum(len(r) for r in qw))
    return qw, scales


def qlinear(x: Row, qw: List[List[int]], scales: List[float]) -> Row:
    out: Row = []
    for i, row in enumerate(qw):
        acc = 0
        for j, q in enumerate(row):
            acc += q * x[j]
        out.append(acc * scales[i])
    bump(len(out))
    return out
