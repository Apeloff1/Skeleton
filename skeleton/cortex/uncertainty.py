"""Uncertainty estimators for adaptive inference and retrieval control."""
from __future__ import annotations

import math
from typing import Sequence


def entropy(probabilities: Sequence[float]) -> float:
    """Natural-log entropy after defensively renormalizing a distribution."""
    if not probabilities:
        return 0.0
    ps = [max(0.0, float(p)) for p in probabilities]
    total = sum(ps)
    if total <= 0.0:
        return 0.0
    return -sum((p / total) * math.log(p / total) for p in ps if p > 0.0)


def normalized_entropy(probabilities: Sequence[float]) -> float:
    if len(probabilities) <= 1:
        return 0.0
    return min(1.0, entropy(probabilities) / math.log(len(probabilities)))


def margin(probabilities: Sequence[float]) -> float:
    """One minus the gap between the top two probabilities."""
    if not probabilities:
        return 1.0
    xs = sorted((max(0.0, float(p)) for p in probabilities), reverse=True)
    total = sum(xs)
    if total <= 0.0:
        return 1.0
    top = xs[0] / total
    second = xs[1] / total if len(xs) > 1 else 0.0
    return max(0.0, min(1.0, 1.0 - (top - second)))


def confidence(probabilities: Sequence[float]) -> float:
    """Blend top-1 confidence with distributional sharpness."""
    if not probabilities:
        return 0.0
    ps = [max(0.0, float(p)) for p in probabilities]
    total = sum(ps)
    if total <= 0.0:
        return 0.0
    top = max(ps) / total
    sharpness = 1.0 - normalized_entropy(ps)
    return max(0.0, min(1.0, 0.65 * top + 0.35 * sharpness))


__all__ = ["confidence", "entropy", "margin", "normalized_entropy"]
