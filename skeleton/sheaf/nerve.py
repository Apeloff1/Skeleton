"""Nerve of the 12-open cover. 1-skeleton is a 12-cycle."""

from __future__ import annotations

from skeleton.sheaf.cards import sheaf_card
from skeleton.sheaf.cech import nerve_edges
from skeleton.sheaf.cover import opens
from skeleton.sheaf.law import COVER_N


def nerve() -> dict:
    verts = opens()
    edges = nerve_edges()
    return {"vertices": verts, "edges": edges, "n": len(verts)}


def nerve_card() -> dict:
    n = nerve()
    ok = n["n"] == COVER_N and len(n["edges"]) == COVER_N
    return sheaf_card(
        kind="nerve",
        hit=1 if ok else 0,
        law="nerve",
        extra={"n": n["n"], "edges": len(n["edges"])},
    )
