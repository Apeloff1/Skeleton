"""Online softmax — FlashAttention-2/4 running max.

Two passes become one. FA4 approx-exp is the optional cheap path.
"""
from __future__ import annotations

import math
from typing import List, Sequence

from skeleton.kernel.ops._stat import bump


def _aexp(v: float) -> float:
    # polynomial stand-in for FA4 faster-exp. Not a CUDA impl.
    x = max(-20.0, min(20.0, v))
    return 1.0 + x + 0.5 * x * x + x * x * x / 6.0


def online(scores: Sequence[float], *, approx: bool = False) -> List[float]:
    if not scores:
        return []
    m = scores[0]
    d = 1.0
    ex = _aexp if approx else math.exp
    ws = [0.0] * len(scores)
    for i, s in enumerate(scores):
        m2 = s if s > m else m
        d = d * ex(m - m2) + ex(s - m2)
        m = m2
        ws[i] = s
    out = [ex(s - m) / (d or 1.0) for s in ws]
    bump(len(out))
    return out
