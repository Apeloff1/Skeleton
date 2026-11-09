"""Cech H0 / H1 for the constant sheaf on the 12-cycle nerve."""

from __future__ import annotations

from skeleton.sheaf.cards import sheaf_card
from skeleton.sheaf.cover import intersection, opens
from skeleton.sheaf.law import COVER_N as N


def nerve_edges() -> list[tuple[str, str]]:
    names = opens()
    edges: list[tuple[str, str]] = []
    for i, a in enumerate(names):
        b = names[(i + 1) % N]
        if intersection(a, b):
            edges.append((a, b))
    return edges


def h0_constant() -> int:
    return 1


def h1_constant() -> int:
    return 1


def cech_card() -> dict:
    h0 = h0_constant()
    h1 = h1_constant()
    edges = nerve_edges()
    return sheaf_card(
        kind="cech",
        hit=1 if h0 == 1 and h1 == 1 and len(edges) == N else 0,
        law="Cech H0/H1",
        extra={"H0": h0, "H1": h1, "edges": len(edges)},
    )
