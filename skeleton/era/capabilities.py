"""GB-36-shaped capability card for era-bind."""

from __future__ import annotations

from typing import Any

from skeleton.era.law import CITATION, HOUSE_ERA, LAYER, PACKET, VERSION


def capabilities() -> dict[str, Any]:
    return {
        "owner": LAYER,
        "packet": PACKET,
        "version": VERSION,
        "contract": {
            "house_era": HOUSE_ERA,
            "verbs": ["plan", "cut", "speak", "forge"],
            "forge_requires_citation": 1,
            "project_root_none_legal": 1,
            "stored_prose": 0,
            "citation": CITATION,
        },
        "failure_modes": ["forge-no-citation", "cut-era-lost", "operator-clobber"],
        "obs": ["era", "reference"],
        "security": {"network": 0, "torch": 0, "hf": 0, "ace": "fail-closed"},
    }
