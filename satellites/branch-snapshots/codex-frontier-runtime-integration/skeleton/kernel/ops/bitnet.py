"""BitNet 1.58 — ternary weight matmul.

W in {-1,0,1}. Activation stays float. Obscure bandwidth win.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def ternarize(w: List[float], *, thresh: float = 0.05) -> List[int]:
    t = max(0.0, float(thresh))
    out = [1 if v > t else (-1 if v < -t else 0) for v in w]
    bump(len(out))
    return out


def bit_dot(x: Row, w: List[int]) -> float:
    return sum((xi if wi > 0 else (-xi if wi < 0 else 0.0)) for xi, wi in zip(x, w))


def bitlinear(x: Row, W: List[List[int]], scale: float = 1.0) -> Row:
    s = float(scale)
    out = [s * bit_dot(x, row) for row in W]
    bump(len(out))
    return out
