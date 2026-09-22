"""Graphs 1.2 facade (GB-18). Thin. No artifacts/Graphs copy."""

from __future__ import annotations

from skeleton.graphs.capabilities import capabilities
from skeleton.graphs.cards import graph_card
from skeleton.graphs.engine import GraphEngine
from skeleton.graphs.export import dot, mermaid
from skeleton.graphs.flow import conserved, flow_card
from skeleton.graphs.gat import gat_card, gat_lite
from skeleton.graphs.house import HOUSE_N, house_card, vertex_ids
from skeleton.graphs.law import PACKET, VERSION
from skeleton.graphs.motifs import motif_card
from skeleton.graphs.spectral import fiedler, lambda_max, spectral_card

__all__ = [
    "HOUSE_N",
    "PACKET",
    "VERSION",
    "GraphEngine",
    "capabilities",
    "conserved",
    "dot",
    "fiedler",
    "flow_card",
    "gat_card",
    "gat_lite",
    "graph_card",
    "house_card",
    "lambda_max",
    "mermaid",
    "motif_card",
    "spectral_card",
    "vertex_ids",
]
