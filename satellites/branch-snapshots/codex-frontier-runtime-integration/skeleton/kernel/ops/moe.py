"""MoE router. Top-1 expert by score. MobileMoE handle."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump


def route(scores: List[float], *, k: int = 1) -> List[int]:
    if not scores:
        return []
    k = max(1, min(int(k), len(scores)))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    bump(k)
    return ranked
