"""Scaled-dot-product attention — the primitive, not a model.

Pure Python. One head. Causal mask. This file has no ModelPort and
no next-token head; transformer.py sits on top of it.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

Vec = List[float]
Mat = List[List[float]]


def zeros(n: int) -> Vec:
    return [0.0] * n


def zeros2(r: int, c: int) -> Mat:
    return [[0.0] * c for _ in range(r)]


def dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b))


def add(a: Vec, b: Vec) -> Vec:
    return [x + y for x, y in zip(a, b)]


def scale(a: Vec, s: float) -> Vec:
    return [x * s for x in a]


def matvec(W: Mat, v: Vec) -> Vec:
    """W is out×in. Returns out."""
    return [dot(row, v) for row in W]


def matvec_T(W: Mat, v: Vec) -> Vec:
    """W is out×in. Returns Wᵀ v (in)."""
    if not W:
        return []
    inn = len(W[0])
    out = zeros(inn)
    for i, row in enumerate(W):
        vi = v[i]
        for j in range(inn):
            out[j] += row[j] * vi
    return out


def outer(a: Vec, b: Vec) -> Mat:
    return [[ai * bj for bj in b] for ai in a]


def add_outer(W: Mat, a: Vec, b: Vec, s: float = 1.0) -> None:
    for i, ai in enumerate(a):
        row = W[i]
        k = ai * s
        for j, bj in enumerate(b):
            row[j] += k * bj


def softmax(xs: Vec) -> Vec:
    if not xs:
        return []
    m = max(xs)
    e = [math.exp(x - m) for x in xs]
    s = sum(e) or 1.0
    return [x / s for x in e]


def causal_attend(Q: Mat, K: Mat, V: Mat) -> Tuple[Mat, Mat]:
    """One head. C[i] = Σ_{j≤i} A[i,j] V[j]. Returns (C, A)."""
    n = len(Q)
    if n == 0:
        return [], []
    d = max(1, len(Q[0]))
    inv = 1.0 / math.sqrt(d)
    C: Mat = []
    A: Mat = []
    for i in range(n):
        scores = [dot(Q[i], K[j]) * inv for j in range(i + 1)]
        w = softmax(scores)
        ctx = zeros(len(V[0]))
        for j, aij in enumerate(w):
            vj = V[j]
            for d_i, val in enumerate(vj):
                ctx[d_i] += aij * val
        C.append(ctx)
        A.append(w)
    return C, A
