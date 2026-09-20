"""GB-36-shaped capability card for circulation."""

from __future__ import annotations

from typing import Any

from skeleton.circulation.law import CITATION, HEAT_DROP, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "shunt_fever": "drop-on-heat",
            "heat_drop": HEAT_DROP,
            "cool_drops": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "cool-path-drop",
            "hot-path-leak",
            "stored_prose-nonzero",
            "artifact-tree-copied",
        ],
        "obs": ["heat_in", "heat_out", "dropped"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
