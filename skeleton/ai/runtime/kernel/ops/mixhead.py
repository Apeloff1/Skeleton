"""Mix heads — convex blend of two attention maps."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def mixhead(a: Row, b: Row, *, gate: float = 0.5) -> Row:
    g = min(1.0, max(0.0, float(gate)))
    n = min(len(a), len(b))
    bump(n)
    return [(1.0 - g) * a[i] + g * b[i] for i in range(n)]
