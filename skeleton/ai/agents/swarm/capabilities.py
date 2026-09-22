"""GB-36-shaped capability card for swarm mesh."""

from __future__ import annotations

from typing import Any

from skeleton.swarm.law import CITATION, LAYER, N_CAP, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "protocol": ["offer", "accept", "refuse", "expire"],
            "n_cap": N_CAP,
            "diet_fork": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["n-cap", "second-diet", "handoff-orphan"],
        "obs": ["accepted", "refused", "expired"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
