"""Native sparse attention — keep top-k logits, zero the rest."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def nsa(logits: Row, *, k: int = 2) -> Row:
    if not logits:
        return []
    kk = max(1, min(int(k), len(logits)))
    order = sorted(range(len(logits)), key=lambda i: logits[i], reverse=True)
    keep = set(order[:kk])
    bump(len(logits))
    return [logits[i] if i in keep else 0.0 for i in range(len(logits))]
