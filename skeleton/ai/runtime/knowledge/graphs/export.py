"""Mermaid and DOT dumps. Non-empty. Pointers only, no stored prose sentences."""

from __future__ import annotations

from skeleton.graphs.cards import graph_card
from skeleton.graphs.house import house_edges, vertex_ids
from skeleton.graphs.law import HOUSE_N


def mermaid() -> str:
    lines = ["graph LR"]
    ids = vertex_ids()
    for i, j in house_edges():
        lines.append("  %s---%s" % (ids[i], ids[j]))
    return "\n".join(lines) + "\n"


def dot() -> str:
    lines = ["graph G {"]
    for i, j in house_edges():
        lines.append("  h%02d -- h%02d;" % (i, j))
    lines.append("}")
    return "\n".join(lines) + "\n"


def export_card() -> dict:
    m = mermaid()
    d = dot()
    ok = len(m) > 0 and len(d) > 0 and "graph" in m and "graph" in d
    return graph_card(
        kind="export",
        hit=1 if ok else 0,
        law="mermaid/dot",
        extra={"mermaid_len": len(m), "dot_len": len(d), "n": HOUSE_N},
    )
