"""Graphs 1.2 facade (GB-18). Thin. No artifacts/Graphs copy."""

from __future__ import annotations

from skeleton.knowledge.graphs.capabilities import capabilities
from skeleton.knowledge.graphs.cards import graph_card
from skeleton.knowledge.graphs.engine import GraphEngine
from skeleton.knowledge.graphs.export import dot, mermaid
from skeleton.knowledge.graphs.flow import conserved, flow_card
from skeleton.knowledge.graphs.gat import gat_card, gat_lite
from skeleton.knowledge.graphs.house import HOUSE_N, house_card, vertex_ids
from skeleton.knowledge.graphs.law import PACKET, VERSION
from skeleton.knowledge.graphs.motifs import motif_card
from skeleton.knowledge.graphs.spectral import fiedler, lambda_max, spectral_card

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
