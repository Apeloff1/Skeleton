"""GB-36-shaped capability card for catalog economy."""

from __future__ import annotations

from typing import Any

from skeleton.economy.law import CITATION, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "bag": "reversible",
            "weights": "sum=1",
            "coin": 0,
            "network_currency": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["weight-drift", "irreversible-bag", "coin-network"],
        "obs": ["sum", "bag_n"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
