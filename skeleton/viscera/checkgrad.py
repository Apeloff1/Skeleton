"""Checkgrad on a 2-layer toy. Tape vs finite difference."""

from __future__ import annotations

from skeleton.viscera.tape import Tape


def toy_loss_and_tape(x0: float, w1: float, w2: float) -> tuple[float, float, float]:
    t = Tape()
    x = t.leaf(x0)
    a = t.leaf(w1)
    b = t.leaf(w2)
    h = t.relu(t.mul(a, x))
    y = t.mul(b, h)
    t.backward(y)
    return y.value, a.grad, b.grad


def finite_dw(x0: float, w1: float, w2: float, eps: float = 1e-5) -> tuple[float, float]:
    def loss(a: float, b: float) -> float:
        h = a * x0
        if h < 0.0:
            h = 0.0
        return b * h

    d1 = (loss(w1 + eps, w2) - loss(w1 - eps, w2)) / (2 * eps)
    d2 = (loss(w1, w2 + eps) - loss(w1, w2 - eps)) / (2 * eps)
    return d1, d2


def checkgrad(x0: float = 1.5, w1: float = 0.8, w2: float = -0.4, tol: float = 1e-3) -> bool:
    _, g1, g2 = toy_loss_and_tape(x0, w1, w2)
    n1, n2 = finite_dw(x0, w1, w2)
    return abs(g1 - n1) < tol and abs(g2 - n2) < tol
