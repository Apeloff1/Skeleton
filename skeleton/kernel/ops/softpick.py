"""Softpick — rectified softmax. No sink, sparse mass.

Cite: arXiv 2504.20966. ReLU on exp, no sum-to-one force.
"""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def softpick(logits: Row) -> Row:
    if not logits:
        return []
    m = max(logits)
    raw = [max(0.0, math.exp(v - m) - math.exp(-m)) for v in logits]
    z = sum(raw) or 1.0
    out = [v / z for v in raw]
    bump(len(out))
    return out


def sink_rate(weights: Row, *, eps: float = 0.3) -> float:
    if not weights:
        return 0.0
    bump(1)
    return 1.0 if weights[0] >= float(eps) else 0.0
