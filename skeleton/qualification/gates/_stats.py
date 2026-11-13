from __future__ import annotations

import math
from typing import Sequence


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile (pct in 0..100)."""
    if not values:
        raise ValueError("percentile of empty sequence")
    if not 0 <= pct <= 100:
        raise ValueError("pct out of range")
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return float(ordered[rank - 1])


def linear_slope(ys: Sequence[float], xs: Sequence[float] | None = None) -> float:
    """Least-squares slope of ys over xs (defaults to 0..n-1)."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(xs) if xs is not None else list(range(n))
    if len(xs) != n:
        raise ValueError("xs and ys differ in length")
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def require(data: dict, *keys: str) -> list[str]:
    return [f"evidence missing '{k}'" for k in keys if k not in data]
