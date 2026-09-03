"""LayerNorm. Mean + var. RMSNorm stays the default house path."""
from __future__ import annotations

import math
from typing import List, Optional

from skeleton.kernel.ops._stat import bump


def layernorm(x: List[float], g: Optional[List[float]] = None, b: Optional[List[float]] = None,
              *, eps: float = 1e-5) -> List[float]:
    n = len(x)
    if n == 0:
        return []
    mean = sum(x) / n
    var = sum((v - mean) ** 2 for v in x) / n
    inv = 1.0 / math.sqrt(var + eps)
    out = []
    for i, v in enumerate(x):
        y = (v - mean) * inv
        if g is not None:
            y *= g[i]
        if b is not None:
            y += b[i]
        out.append(y)
    bump(n)
    return out
