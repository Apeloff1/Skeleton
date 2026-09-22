"""GB-36-shaped capability card. Empty registry elsewhere is legal."""

from __future__ import annotations

from typing import Any

from skeleton.primitives.law import CITATION, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "kinds": 12,
            "ring_cap": 24,
            "stored_prose": 0,
            "viscera_import": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "kind-count-grew",
            "ring-over-cap",
            "stored_prose-nonzero",
            "viscera-imported",
            "merkle-mismatch",
        ],
        "obs": ["kind_count", "ring_size", "merkle_root", "hit"],
        "security": {
            "network": 0,
            "torch": 0,
            "hf": 0,
            "ace": "fail-closed",
        },
    }
