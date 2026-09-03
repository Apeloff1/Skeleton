"""Scale / clamp / dropout-off. Infer helpers."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump


def scale(xs: List[float], s: float) -> List[float]:
    out = [v * s for v in xs]
    bump(len(out))
    return out


def clamp(xs: List[float], lo: float = -1.0, hi: float = 1.0) -> List[float]:
    out = [lo if v < lo else hi if v > hi else v for v in xs]
    bump(len(out))
    return out


def dropout(xs: List[float], p: float = 0.0) -> List[float]:
    # Infer: p ignored, identity. Training dropout is not house path.
    bump(len(xs))
    return list(xs)
