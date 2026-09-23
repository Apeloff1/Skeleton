"""GB-36-shaped capability card for the cue organ."""

from __future__ import annotations

from typing import Any

from skeleton.cue.law import AXES, CITATION, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "axes": len(AXES),
            "vocab": "closed",
            "stimulus": "drop",
            "sentence": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["stimulus-kept", "open-vocab", "axis-freeze"],
        "obs": ["i", "last", "tokens"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
