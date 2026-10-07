"""GB-36-shaped capability card for TurnEngine."""

from __future__ import annotations

from typing import Any

from skeleton.turn.law import CITATION, LAYER, PACKET, TICKS, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "verbs": ["extract", "heat", "sleep"],
            "dream": "improve-sleep",
            "ticks": TICKS,
            "warp": "extract-once",
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["extract-warp-mismatch", "token-every-frame", "gui-required"],
        "obs": ["ticks", "extract_count", "warp_count"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
