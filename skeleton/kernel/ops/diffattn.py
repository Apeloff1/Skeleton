"""Differential attention — subtract a noise head from the signal head."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def diffattn(signal: Row, noise: Row, *, lam: float = 0.5) -> Row:
    n = min(len(signal), len(noise))
    bump(n)
    return [signal[i] - float(lam) * noise[i] for i in range(n)]
