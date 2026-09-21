"""GB-36-shaped capability card for chronicle helix."""

from __future__ import annotations

from typing import Any

from skeleton.chronicle.law import CITATION, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "helix": "jsonl",
            "append": True,
            "verify": True,
            "tamper_detect": True,
            "network": 0,
            "coin": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "broken-link",
            "tamper-missed",
            "coin-wording",
            "stored_prose-nonzero",
        ],
        "obs": ["n", "tip", "ok"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
