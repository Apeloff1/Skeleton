"""Logit lens: last hidden through unembed. No torch."""

from __future__ import annotations

import math
from typing import Sequence


def logits(h: Sequence[float], weight: Sequence[Sequence[float]]) -> list[float]:
    out = []
    for row in weight:
        out.append(sum(a * b for a, b in zip(h, row)))
    return out


def softmax(xs: Sequence[float]) -> list[float]:
    m = max(xs) if xs else 0.0
    ex = [math.exp(v - m) for v in xs]
    s = sum(ex) or 1.0
    return [v / s for v in ex]


def lens(h: Sequence[float], weight: Sequence[Sequence[float]]) -> tuple[int, list[float]]:
    p = softmax(logits(h, weight))
    idx = max(range(len(p)), key=lambda i: p[i]) if p else -1
    return idx, p
