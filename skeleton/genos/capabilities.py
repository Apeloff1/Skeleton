"""GB-36-shaped capability card for DNAHelix / genos."""

from __future__ import annotations

from typing import Any

from skeleton.genos.law import CITATION, HELIX_NAME, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "emit": "forge-pair",
            "read": "genos-coil",
            "helix_file": HELIX_NAME,
            "genome_prose": 0,
            "chain": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["no-pair-after-forge", "genome-prose", "helix-as-chain"],
        "obs": ["n", "path"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
