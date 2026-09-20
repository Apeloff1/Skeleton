"""Tiny vector math. No torch. No numpy."""

from __future__ import annotations

import math
from typing import Sequence

Vec = list[float]


def rms(xs: Sequence[float], eps: float = 1e-6) -> float:
    if not xs:
        return 0.0
    return math.sqrt(sum(v * v for v in xs) / len(xs) + eps)


def normalize_rms(xs: Sequence[float], eps: float = 1e-6) -> Vec:
    s = rms(xs, eps)
    return [v / s for v in xs]


def add(a: Sequence[float], b: Sequence[float]) -> Vec:
    return [x + y for x, y in zip(a, b)]


def scale(xs: Sequence[float], a: float) -> Vec:
    return [a * v for v in xs]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def snr_db(signal: Sequence[float], recon: Sequence[float]) -> float:
    num = sum(v * v for v in signal)
    den = sum((s - r) * (s - r) for s, r in zip(signal, recon))
    if den <= 0.0:
        return float("inf")
    return 10.0 * math.log10(num / den)
