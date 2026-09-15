"""Softmax. Online max+sum so S is not stored."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump


def softmax(xs: List[float]) -> List[float]:
    if not xs:
        return []
    m = max(xs)
    ex = [math.exp(x - m) for x in xs]
    z = sum(ex) or 1.0
    out = [v / z for v in ex]
    bump(len(out))
    return out
