"""Muon Newton-Schulz orthogonalization. 2x2 lite. No torch."""

from __future__ import annotations

Mat = list[list[float]]


def _mm(a: Mat, b: Mat) -> Mat:
    return [
        [a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1]],
        [a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1]],
    ]


def _add(a: Mat, b: Mat) -> Mat:
    return [[a[i][j] + b[i][j] for j in range(2)] for i in range(2)]


def _scale(a: Mat, s: float) -> Mat:
    return [[a[i][j] * s for j in range(2)] for i in range(2)]


def _t(a: Mat) -> Mat:
    return [[a[0][0], a[1][0]], [a[0][1], a[1][1]]]


def newton_schulz(x: Mat, steps: int = 5) -> Mat:
    cur = [row[:] for row in x]
    nrm = max(abs(cur[i][j]) for i in range(2) for j in range(2)) or 1.0
    cur = _scale(cur, 1.0 / nrm)
    for _ in range(steps):
        xtx = _mm(_t(cur), cur)
        cur = _add(_scale(cur, 1.5), _scale(_mm(cur, xtx), -0.5))
    return cur


def frobenius(a: Mat) -> float:
    return sum(a[i][j] * a[i][j] for i in range(2) for j in range(2)) ** 0.5


def near_orthogonal(x: Mat, tol: float = 0.35) -> bool:
    gram = _mm(_t(x), x)
    ident = [[1.0, 0.0], [0.0, 1.0]]
    err = frobenius(_add(gram, _scale(ident, -1.0)))
    return err < tol
