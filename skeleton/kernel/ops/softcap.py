"""Logit / score softcap — Gemma-2 tanh cap.

Superfluous if temp already damps, required when scores explode.
"""
from __future__ import annotations

import math
from typing import List, Sequence

from skeleton.kernel.ops._stat import bump


def softcap(xs: Sequence[float], *, cap: float = 50.0) -> List[float]:
    c = max(1e-6, float(cap))
    out = [c * math.tanh(v / c) for v in xs]
    bump(len(out))
    return out


def attn_softcap(scores: Sequence[float], *, cap: float = 50.0) -> List[float]:
    return softcap(scores, cap=cap)
