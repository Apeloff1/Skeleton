"""Pure-Python silu / gelu / rms_norm. No torch. CI safe."""

from __future__ import annotations

import math
from typing import Sequence

from skeleton.primitives.cards import primitive_card
from skeleton.primitives.errors import KindError


def silu(x: float) -> float:
    return x * (1.0 / (1.0 + math.exp(-x)))


def gelu(x: float) -> float:
    return 0.5 * x * (1.0 + math.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x * x * x)))


def rms_norm(xs: Sequence[float], eps: float = 1e-6) -> list[float]:
    if not xs:
        return []
    mean_sq = sum(v * v for v in xs) / len(xs)
    denom = math.sqrt(mean_sq + eps)
    return [v / denom for v in xs]


def apply(name: str, xs: Sequence[float]) -> list[float]:
    if name == "silu":
        return [silu(v) for v in xs]
    if name == "gelu":
        return [gelu(v) for v in xs]
    if name == "rms_norm":
        return rms_norm(xs)
    raise KindError(name)


def activation_card(name: str, xs: Sequence[float]) -> dict:
    out = apply(name, xs)
    finite = all(math.isfinite(v) for v in out)
    return primitive_card(
        kind=name,
        hit=1 if finite else 0,
        law="activation finite",
        extra={"n": len(out), "finite": int(finite)},
    )
