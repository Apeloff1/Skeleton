"""Walsh–Hadamard rotate — QuaRot / QuIP# pre-quant mix.

Obscure. Mixes axes so outliers do not sit on one channel.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump

Row = List[float]


def _pad2(xs: Row) -> Row:
    n = 1
    while n < len(xs):
        n *= 2
    return list(xs) + [0.0] * (n - len(xs))


def hadamard(xs: Row) -> Row:
    h = _pad2(xs)
    n = len(h)
    length = 1
    while length < n:
        for i in range(0, n, 2 * length):
            for j in range(length):
                a = h[i + j]
                b = h[i + j + length]
                h[i + j] = a + b
                h[i + j + length] = a - b
        length *= 2
    inv = n ** 0.5 or 1.0
    out = [v / inv for v in h[: len(xs)]]
    bump(len(out))
    return out
