"""House graph. Vertex count frozen at 27."""

from __future__ import annotations

from skeleton.graphs.cards import graph_card
from skeleton.graphs.law import HOUSE_N

__all__ = ["HOUSE_N", "adjacency", "degree", "house_card", "house_edges", "laplacian", "vertex_ids"]


def vertex_ids(n: int = HOUSE_N) -> list[str]:
    if n != HOUSE_N:
        raise ValueError("house-n")
    return ["h%02d" % i for i in range(n)]


def house_edges(n: int = HOUSE_N) -> list[tuple[int, int]]:
    if n != HOUSE_N:
        raise ValueError("house-n")
    edges: set[tuple[int, int]] = set()
    for i in range(n):
        for d in (1, 2):
            j = (i + d) % n
            a, b = (i, j) if i < j else (j, i)
            edges.add((a, b))
    return sorted(edges)


def adjacency(n: int = HOUSE_N) -> list[list[float]]:
    a = [[0.0] * n for _ in range(n)]
    for i, j in house_edges(n):
        a[i][j] = 1.0
        a[j][i] = 1.0
    return a


def degree(a: list[list[float]]) -> list[float]:
    return [sum(row) for row in a]


def laplacian(a: list[list[float]]) -> list[list[float]]:
    n = len(a)
    deg = degree(a)
    l = [[0.0] * n for _ in range(n)]
    for i in range(n):
        l[i][i] = deg[i]
        for j in range(n):
            l[i][j] -= a[i][j]
    return l


def house_card() -> dict:
    verts = vertex_ids()
    return graph_card(
        kind="house",
        hit=1 if len(verts) == HOUSE_N else 0,
        law="house n=27",
        extra={"n": len(verts), "vertices": verts},
    )
