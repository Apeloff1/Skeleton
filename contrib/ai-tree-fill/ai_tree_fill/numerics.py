"""Deterministic numerics. No model authority. Pure Python."""

from __future__ import annotations

import math
from typing import Sequence

from ai_tree_fill.laws import LawBreak, clip

G_CLIP_LOCAL = 8.0


def rmsnorm(vec: Sequence[float], eps: float = 1e-6) -> list[float]:
    if not vec:
        raise LawBreak("rmsnorm", "empty vector")
    mean_sq = sum(x * x for x in vec) / len(vec)
    return [x / math.sqrt(mean_sq + eps) for x in vec]


def silu(vec: Sequence[float]) -> list[float]:
    out = []
    for x in vec:
        x = clip(x, -40.0, 40.0)
        sig = 1.0 / (1.0 + math.exp(-x))
        out.append(x * sig)
    return out


def softmax(vec: Sequence[float]) -> list[float]:
    if not vec:
        raise LawBreak("softmax", "empty vector")
    peak = max(vec)
    exps = [math.exp(clip(x - peak, -60.0, 0.0)) for x in vec]
    total = sum(exps)
    return [e / total for e in exps]


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise LawBreak("dot", "length mismatch")
    return sum(x * y for x, y in zip(a, b))


def matvec(matrix: Sequence[Sequence[float]], vec: Sequence[float]) -> list[float]:
    if not matrix or len(matrix[0]) != len(vec):
        raise LawBreak("matvec", "shape mismatch")
    return [dot(row, vec) for row in matrix]


def transpose(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    return [list(col) for col in zip(*matrix)]


def _apply_reflector(block: list[list[float]], v: Sequence[float]) -> None:
    rows = len(block)
    cols = len(block[0]) if block else 0
    for j in range(cols):
        coeff = 2.0 * sum(v[i] * block[i][j] for i in range(rows))
        for i in range(rows):
            block[i][j] -= coeff * v[i]


def householder_qr(matrix: Sequence[Sequence[float]]) -> tuple[list[list[float]], list[list[float]]]:
    """Thin Householder QR. A = Q R for full-column rank."""
    a = [list(row) for row in matrix]
    m = len(a)
    n = len(a[0]) if a else 0
    if m == 0 or n == 0 or m < n:
        raise LawBreak("qr", "need m >= n > 0")
    q = [[1.0 if i == j else 0.0 for j in range(m)] for i in range(m)]
    for k in range(n):
        col = [a[i][k] for i in range(k, m)]
        norm = math.sqrt(sum(x * x for x in col))
        if norm < 1e-12:
            raise LawBreak("qr", f"rank drop at column {k}")
        sign = 1.0 if col[0] >= 0 else -1.0
        u = list(col)
        u[0] += sign * norm
        u_norm = math.sqrt(sum(x * x for x in u))
        v = [x / u_norm for x in u]
        sub = [a[i][k:] for i in range(k, m)]
        _apply_reflector(sub, v)
        for i, row in enumerate(sub):
            a[k + i][k:] = row
        q_sub = [q[i][k:] for i in range(m)]
        # Reflect columns of Q from the left on rows k:.
        q_rows = [q[i][:] for i in range(k, m)]
        _apply_reflector(q_rows, v)
        for i, row in enumerate(q_rows):
            q[k + i] = row
        del q_sub
    q_thin = transpose(q)
    q_thin = [q_thin[i][:n] for i in range(m)]
    r_thin = [[a[i][j] if i <= j else 0.0 for j in range(n)] for i in range(n)]
    return q_thin, r_thin


def conjugate_gradient(
    matrix: Sequence[Sequence[float]],
    b: Sequence[float],
    steps: int = 8,
) -> list[float]:
    n = len(b)
    x = [0.0] * n
    r = [b[i] - matvec(matrix, x)[i] for i in range(n)]
    p = list(r)
    rs = dot(r, r)
    for _ in range(steps):
        ap = matvec(matrix, p)
        denom = dot(p, ap)
        if abs(denom) < 1e-12:
            raise LawBreak("cg", "non-spd or stall")
        alpha = clip(rs / denom, -G_CLIP_LOCAL, G_CLIP_LOCAL)
        x = [clip(x[i] + alpha * p[i], -1e3, 1e3) for i in range(n)]
        r = [r[i] - alpha * ap[i] for i in range(n)]
        rs_next = dot(r, r)
        if rs_next < 1e-12:
            return x
        beta = rs_next / rs
        p = [r[i] + beta * p[i] for i in range(n)]
        rs = rs_next
    return x


def qk_scores(q: Sequence[float], keys: Sequence[Sequence[float]]) -> list[float]:
    qn = silu(rmsnorm(q))
    raw = [dot(qn, rmsnorm(k)) for k in keys]
    return softmax(raw)
