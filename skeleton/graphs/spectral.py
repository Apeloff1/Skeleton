"""lambda_max of adjacency and Fiedler value of Laplacian. Pure Python."""

from __future__ import annotations

from skeleton.graphs.cards import graph_card
from skeleton.graphs.house import adjacency, laplacian
from skeleton.graphs.law import HOUSE_N, POWER_ITERS
from skeleton.graphs.linalg import deflate, normalize, power_iter


def lambda_max(a: list[list[float]] | None = None) -> tuple[float, list[float]]:
    if a is None:
        a = adjacency()
    return power_iter(a, POWER_ITERS)


def fiedler(l: list[list[float]] | None = None) -> tuple[float, list[float]]:
    if l is None:
        l = laplacian(adjacency())
    n = len(l)
    mu = 8.0
    m = [[(mu if i == j else 0.0) - l[i][j] for j in range(n)] for i in range(n)]
    lam1, v1 = power_iter(m, POWER_ITERS)
    m2 = deflate(m, normalize(v1), lam1)
    lam2, v2 = power_iter(m2, POWER_ITERS)
    fied = mu - lam2
    return fied, v2


def spectral_card() -> dict:
    a = adjacency()
    lmax, _ = lambda_max(a)
    fval, _ = fiedler()
    ok = lmax > 0.0 and fval >= -1e-6
    return graph_card(
        kind="spectral",
        hit=1 if ok else 0,
        law="lambda_max + Fiedler",
        extra={"lambda_max": lmax, "fiedler": fval, "n": HOUSE_N},
    )
