"""Compose house + spectral + flow + motifs + gat + export."""

from __future__ import annotations

from typing import Any

from skeleton.graphs.cards import graph_card
from skeleton.graphs.export import dot, export_card, mermaid
from skeleton.graphs.flow import flow_card
from skeleton.graphs.gat import gat_card
from skeleton.graphs.house import HOUSE_N, house_card
from skeleton.graphs.motifs import motif_card
from skeleton.graphs.spectral import spectral_card


class GraphEngine:
    def snapshot(self) -> dict[str, Any]:
        house = house_card()
        spec = spectral_card()
        flow = flow_card()
        motifs = motif_card()
        gat = gat_card()
        exp = export_card()
        hits = [c["hit"] for c in (house, spec, flow, motifs, gat, exp)]
        ok = all(h == 1 for h in hits) and house.get("n") == HOUSE_N
        return graph_card(
            kind="graphs",
            hit=1 if ok else 0,
            law="graphs 1.2",
            extra={
                "house_n": house.get("n"),
                "lambda_max": spec.get("lambda_max"),
                "fiedler": spec.get("fiedler"),
                "flow_ok": flow.get("ok"),
                "wedges": motifs.get("wedges"),
                "gat": gat.get("row_stochastic"),
                "mermaid_len": exp.get("mermaid_len"),
                "dot_preview": dot().splitlines()[0],
                "mermaid_preview": mermaid().splitlines()[0],
            },
        )
