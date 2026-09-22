"""Damped RK substeps — loop a frozen checkpoint as an ODE.

Cite: frozen-loop RK (alphaXiv May 2026). No new weights.
"""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.loop import block

Row = List[float]


def _sub(a: Row, b: Row) -> Row:
    return [x - y for x, y in zip(a, b)]


def _add(a: Row, b: Row, s: float = 1.0) -> Row:
    return [x + s * y for x, y in zip(a, b)]


def rk4(x: Row, *, damp: float = 0.5) -> dict:
    # treat block(x)-x as f(x)
    k1 = _sub(block(x), x)
    x2 = _add(x, k1, 0.5)
    k2 = _sub(block(x2), x2)
    x3 = _add(x, k2, 0.5)
    k3 = _sub(block(x3), x3)
    x4 = _add(x, k3, 1.0)
    k4 = _sub(block(x4), x4)
    d = max(0.0, min(1.0, float(damp)))
    step = [(k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6.0 for i in range(len(x))]
    y = [x[i] + d * step[i] for i in range(len(x))]
    bump(len(y))
    return {
        "kind": "rk4-loop",
        "damp": d,
        "h": y,
        "stored_prose": 0,
    }
