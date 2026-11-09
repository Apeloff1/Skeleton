"""SwiGLU: silu(xW) * (xV). One working row."""
from __future__ import annotations

import math
from typing import List

from skeleton.kernel.ops._stat import bump


def silu(x: float) -> float:
    return x / (1.0 + math.exp(-x))


def swiglu(gate: List[float], up: List[float]) -> List[float]:
    n = min(len(gate), len(up))
    out = [silu(gate[i]) * up[i] for i in range(n)]
    bump(n)
    return out
