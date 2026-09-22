"""GB-36-shaped capability card for Graphs 1.2."""

from __future__ import annotations

from typing import Any

from skeleton.graphs.law import CITATION, HOUSE_N, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "house_n": HOUSE_N,
            "spectral": ["lambda_max", "fiedler"],
            "flow": "conserved",
            "motifs": True,
            "gat": "lite",
            "export": ["mermaid", "dot"],
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "house-n-not-27",
            "flow-not-conserved",
            "empty-mermaid",
            "stored_prose-nonzero",
            "artifact-tree-copied",
        ],
        "obs": ["lambda_max", "fiedler", "wedges", "triangles", "flow_ok"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
