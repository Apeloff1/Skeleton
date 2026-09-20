"""GB-36-shaped capability card for Sheaf 1.1."""

from __future__ import annotations

from typing import Any

from skeleton.sheaf.law import CITATION, COVER_N, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "cover_n": COVER_N,
            "restrict": "exact r composed r",
            "glue": "skip cite/feed",
            "stalk": True,
            "cech": ["H0", "H1"],
            "nerve": True,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "cover-not-12",
            "r-compose-r-fail",
            "glued-cite-cycle",
            "stored_prose-nonzero",
            "artifact-tree-copied",
        ],
        "obs": ["H0", "H1", "cover_n", "exact"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
