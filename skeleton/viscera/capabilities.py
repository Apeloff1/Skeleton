"""GB-36-shaped capability card for Viscera 2.5."""

from __future__ import annotations

from typing import Any

from skeleton.viscera.law import CITATION, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "qk_norm": "rms",
            "specdec": "accept-until-mismatch",
            "steer": "h += alpha u-hat",
            "quant": "absmax int8",
            "remat": "identity",
            "torch": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": [
            "specdec-past-mismatch",
            "snr-nonfinite",
            "remat-drift",
            "torch-imported",
            "stored_prose-nonzero",
            "artifact-tree-copied",
        ],
        "obs": ["accepted", "snr", "identity", "score"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
