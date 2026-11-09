"""GB-36-shaped capability card for HOAG 1.0."""

from __future__ import annotations

from typing import Any

from skeleton.hoag.law import CITATION, LAYER, PACKET, REGION_N, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "regions": REGION_N,
            "warp": "extract-once",
            "bind": "mouth/body",
            "organism_pwa": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "region-count",
            "warp-twice",
            "unbind-mouth-body",
            "pwa-copied",
            "stored_prose-nonzero",
        ],
        "obs": ["regions", "skipped", "bound"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
