"""GB-36-shaped capability card for parse-pointer."""

from __future__ import annotations

from typing import Any

from skeleton.parse.law import CITATION, LAYER, N_CAP, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "forms": ["arxiv/abs", "github.com"],
            "n_cap": N_CAP,
            "mesh_sentence": 0,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["stored-sentence", "n-cap-spill", "prose-mesh"],
        "obs": ["n", "dropped", "hit"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
