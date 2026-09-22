"""GAT-lite. One head. Softmax over neighbors. No torch."""

from __future__ import annotations

import math

from skeleton.graphs.cards import graph_card
from skeleton.graphs.house import adjacency, vertex_ids
from skeleton.graphs.law import GAT_HEADS, HOUSE_N


def leaky_relu(x: float, alpha: float = 0.2) -> float:
    return x if x >= 0.0 else alpha * x


def softmax(xs: list[float]) -> list[float]:
    if not xs:
        return []
    m = max(xs)
    ex = [math.exp(v - m) for v in xs]
    s = sum(ex)
    return [v / s for v in ex]


def gat_lite(features: list[float] | None = None) -> list[list[float]]:
    a = adjacency()
    n = HOUSE_N
    if features is None:
        features = [float(i) for i in range(n)]
    attn: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        nbrs = [j for j in range(n) if a[i][j] > 0.0 or i == j]
        scores = [leaky_relu(features[i] + features[j]) for j in nbrs]
        weights = softmax(scores)
        for j, w in zip(nbrs, weights):
            attn[i][j] = w
    return attn


def gat_card() -> dict:
    attn = gat_lite()
    rows_sum = [sum(row) for row in attn]
    ok = all(abs(s - 1.0) < 1e-6 for s in rows_sum)
    return graph_card(
        kind="gat",
        hit=1 if ok else 0,
        law="GAT-lite",
        extra={"heads": GAT_HEADS, "n": HOUSE_N, "row_stochastic": int(ok), "ids": vertex_ids()[:3]},
    )
