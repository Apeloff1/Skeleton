"""Tiny dense linear algebra for n=27. No numpy. No torch."""

from __future__ import annotations

import math
from typing import Sequence


Matrix = list[list[float]]
Vector = list[float]


def zeros(n: int) -> Matrix:
    return [[0.0] * n for _ in range(n)]


def ident(n: int) -> Matrix:
    m = zeros(n)
    for i in range(n):
        m[i][i] = 1.0
    return m


def matvec(a: Matrix, x: Sequence[float]) -> Vector:
    return [sum(a[i][j] * x[j] for j in range(len(x))) for i in range(len(a))]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def nrm2(x: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in x))


def scale(x: Sequence[float], s: float) -> Vector:
    return [v * s for v in x]


def add(x: Sequence[float], y: Sequence[float]) -> Vector:
    return [a + b for a, b in zip(x, y)]


def sub(x: Sequence[float], y: Sequence[float]) -> Vector:
    return [a - b for a, b in zip(x, y)]


def normalize(x: Sequence[float]) -> Vector:
    n = nrm2(x)
    if n == 0.0:
        return list(x)
    return [v / n for v in x]


def power_iter(a: Matrix, iters: int, seed: Sequence[float] | None = None) -> tuple[float, Vector]:
    n = len(a)
    x = list(seed) if seed is not None else [1.0] + [0.1] * (n - 1)
    x = normalize(x)
    lam = 0.0
    for _ in range(iters):
        y = matvec(a, x)
        lam = dot(x, y)
        x = normalize(y)
    return lam, x


def deflate(a: Matrix, vec: Sequence[float], lam: float) -> Matrix:
    n = len(a)
    out = zeros(n)
    for i in range(n):
        for j in range(n):
            out[i][j] = a[i][j] - lam * vec[i] * vec[j]
    return out
