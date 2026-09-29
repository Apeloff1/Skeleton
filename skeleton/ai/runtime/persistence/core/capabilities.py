"""GB-36-shaped capability card for persist 1.0."""

from __future__ import annotations

from typing import Any

from skeleton.persist.law import CITATION, LAYER, OWN_ENV, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "env": OWN_ENV,
            "unset": "live_deck/live_jeeves",
            "set": "helix+rotors+traces",
            "cores": 1,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "second-core",
            "unset-writes-disk",
            "set-skips-disk",
            "stored_prose-nonzero",
        ],
        "obs": ["gate", "slot"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
