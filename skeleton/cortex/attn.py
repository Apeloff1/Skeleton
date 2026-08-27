"""Scaled-dot-product attention — the primitive, not a model.

Pure Python. Causal mask. Multi-head is split/concat over this.
LayerNorm + full-sequence MHA backward live here so transformer.py
can stack blocks without copying the guts. No ModelPort.
"""
from __future__ import annotations

import math
from typing import List, Tuple

Vec = List[float]
Mat = List[List[float]]


def zeros(n: int) -> Vec:
    return [0.0] * n


def ones(n: int) -> Vec:
    return [1.0] * n


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


def relu(xs: Vec) -> Vec:
    return [x if x > 0.0 else 0.0 for x in xs]


def layer_norm(x: Vec, g: Vec, b: Vec, eps: float = 1e-5) -> Tuple[Vec, Vec, float]:
    """Pre-LN. Returns (y, hat, inv). hat is mean-0 unit-var; y = g⊙hat + b."""
    n = max(1, len(x))
    mean = sum(x) / n
    var = sum((xi - mean) ** 2 for xi in x) / n
    inv = 1.0 / math.sqrt(var + eps)
    hat = [(xi - mean) * inv for xi in x]
    y = [g[i] * hat[i] + b[i] for i in range(len(x))]
    return y, hat, inv


def layer_norm_bwd(dy: Vec, hat: Vec, inv: float, g: Vec) -> Tuple[Vec, Vec, Vec]:
    """dL/dx, dL/dg, dL/db given dL/dy and the forward cache."""
    n = max(1, len(dy))
    dhat = [dy[i] * g[i] for i in range(n)]
    dg = [dy[i] * hat[i] for i in range(n)]
    db = list(dy)
    mean_dhat = sum(dhat) / n
    mean_dhat_hat = sum(dhat[i] * hat[i] for i in range(n)) / n
    dx = [inv * (dhat[i] - mean_dhat - hat[i] * mean_dhat_hat) for i in range(n)]
    return dx, dg, db


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


def slice_head(X: Mat, h: int, n_heads: int) -> Mat:
    if not X:
        return []
    d = len(X[0])
    n_heads = max(1, n_heads)
    dh = max(1, d // n_heads)
    lo, hi = h * dh, (h + 1) * dh
    return [row[lo:hi] for row in X]


def concat_heads(heads: List[Mat]) -> Mat:
    if not heads:
        return []
    n = len(heads[0])
    out: Mat = []
    for i in range(n):
        row: Vec = []
        for H in heads:
            row.extend(H[i])
        out.append(row)
    return out


def multi_head_attend(Q: Mat, K: Mat, V: Mat, n_heads: int = 1) -> Tuple[Mat, List[Mat]]:
    """n_heads independent causal attends, concat on the feature axis."""
    n_heads = max(1, int(n_heads))
    if n_heads == 1:
        C, A = causal_attend(Q, K, V)
        return C, [A]
    Cs: List[Mat] = []
    As: List[Mat] = []
    for h in range(n_heads):
        C, A = causal_attend(
            slice_head(Q, h, n_heads),
            slice_head(K, h, n_heads),
            slice_head(V, h, n_heads),
        )
        Cs.append(C)
        As.append(A)
    return concat_heads(Cs), As


def mha_backward(
    dC: Mat, Q: Mat, K: Mat, V: Mat, As: List[Mat], n_heads: int,
) -> Tuple[Mat, Mat, Mat]:
    """Full-sequence multi-head backward. Returns (dQ, dK, dV) in concat space."""
    n = len(dC)
    if n == 0:
        return [], [], []
    D = len(dC[0])
    heads = max(1, int(n_heads))
    dh = max(1, D // heads)
    dQ = [zeros(D) for _ in range(n)]
    dK = [zeros(D) for _ in range(n)]
    dV = [zeros(D) for _ in range(n)]
    inv = 1.0 / math.sqrt(dh)
    for h in range(heads):
        lo = h * dh
        Qh = slice_head(Q, h, heads)
        Kh = slice_head(K, h, heads)
        Vh = slice_head(V, h, heads)
        Ah = As[h] if h < len(As) else []
        for i in range(n):
            dCh = dC[i][lo:lo + dh]
            w = Ah[i] if i < len(Ah) else []
            dAh = zeros(len(w))
            for j, aij in enumerate(w):
                for d in range(len(dCh)):
                    dV[j][lo + d] += dCh[d] * aij
                dAh[j] = sum(dCh[d] * Vh[j][d] for d in range(len(dCh)))
            dot_da = sum(dAh[j] * w[j] for j in range(len(w)))
            ds = [(dAh[j] - dot_da) * w[j] for j in range(len(w))]
            Qi = Qh[i]
            for j, dsj in enumerate(ds):
                g = dsj * inv
                Khj = Kh[j]
                for d in range(dh):
                    dQ[i][lo + d] += Khj[d] * g
                    dK[j][lo + d] += Qi[d] * g
    return dQ, dK, dV
