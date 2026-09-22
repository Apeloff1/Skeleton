"""GB-36-shaped capability card for telemetry SSE."""

from __future__ import annotations

from typing import Any

from skeleton.telemetry.law import CITATION, DEFAULT_ON, LAYER, PACKET, PATH, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "path": PATH,
            "default_on": DEFAULT_ON,
            "payload_prose": 0,
            "mobile": "skip",
            "operator_routes": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["default-on", "prose-payload", "operator-clobber", "mobile-stream"],
        "obs": ["n", "open"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
