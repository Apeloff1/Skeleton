"""Triangle and wedge counts on the house circulant."""

from __future__ import annotations

from skeleton.graphs.cards import graph_card
from skeleton.graphs.house import adjacency
from skeleton.graphs.law import HOUSE_N


def count_wedges(a: list[list[float]]) -> int:
    n = len(a)
    total = 0
    for i in range(n):
        deg = int(sum(a[i]))
        total += deg * (deg - 1) // 2
    return total


def count_triangles(a: list[list[float]]) -> int:
    n = len(a)
    tri = 0
    for i in range(n):
        for j in range(i + 1, n):
            if a[i][j] == 0.0:
                continue
            for k in range(j + 1, n):
                if a[i][k] and a[j][k]:
                    tri += 1
    return tri


def motif_card() -> dict:
    a = adjacency()
    wedges = count_wedges(a)
    triangles = count_triangles(a)
    return graph_card(
        kind="motif",
        hit=1 if wedges > 0 else 0,
        law="motifs",
        extra={"wedges": wedges, "triangles": triangles, "n": HOUSE_N},
    )
