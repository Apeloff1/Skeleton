"""GB-36-shaped capability card for Motive 1.0."""

from __future__ import annotations

from typing import Any

from skeleton.motive.law import CITATION, HEART_H0, LAYER, PACKET, SPINE_BUS, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "unit": "S",
            "suspend": "Sigma",
            "loop": "Omega",
            "smash": True,
            "omega_sigma": "id",
            "map_s_s": "S",
            "heart_h0": HEART_H0,
            "spine_bus": SPINE_BUS,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "omega-sigma-not-id",
            "map-ss-not-s",
            "heart-not-1",
            "spine-imported",
            "stored_prose-nonzero",
            "artifact-tree-copied",
        ],
        "obs": ["H0", "iso", "map_ss"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
