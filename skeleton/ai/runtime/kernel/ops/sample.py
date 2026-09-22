"""Sampling kernel. Greedy or top-k. No nucleus essay."""
from __future__ import annotations

import math
from typing import List, Sequence

from skeleton.kernel.ops._stat import bump


def sample(logits: Sequence[float], *, k: int = 1, temp: float = 1.0) -> int:
    if not logits:
        return 0
    if k <= 1:
        bump(1)
        return max(range(len(logits)), key=lambda i: logits[i])
    k = min(int(k), len(logits))
    ranked = sorted(range(len(logits)), key=lambda i: logits[i], reverse=True)[:k]
    t = max(1e-6, float(temp))
    ws = [math.exp(logits[i] / t) for i in ranked]
    z = sum(ws) or 1.0
    # deterministic pick of the massiest bin — no RNG in the house path
    pick = ranked[max(range(len(ws)), key=lambda j: ws[j] / z)]
    bump(1)
    return pick
