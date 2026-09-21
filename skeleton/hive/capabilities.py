"""GB-36-shaped capability card for Hive 1.0."""

from __future__ import annotations

from typing import Any

from skeleton.hive.law import CITATION, LAYER, PACKET, VERSION, WALK_CAP


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "mint": True,
            "link": True,
            "card_root": True,
            "gossip": True,
            "walk_cap": WALK_CAP,
            "tick": True,
            "chain": 0,
            "coin": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "walk-over-cap",
            "gossip-history-empty",
            "chain-wording",
            "coin-wording",
            "stored_prose-nonzero",
        ],
        "obs": ["root", "n_history", "path", "ticks"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
