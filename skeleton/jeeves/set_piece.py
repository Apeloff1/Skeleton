"""Set piece — Pareto memorable moment inside a stage.

A designed peak that proves the fantasy without breaking fairness.
"""

from __future__ import annotations

from typing import Any


def set_piece(name: str, verb: str = "use") -> dict[str, Any]:
    return {
        "name": name,
        "core_verb": verb,
        "requirements": [
            "Readable setup",
            "Clear goal",
            "Fair clue or teach",
            "Strong feedback on success",
            "Recovery or exit after",
        ],
        "anti_patterns": ["unclued instant fail", "required pixel hunt", "soft-lock on fail"],
        "place": "Near the intensity peak of the stage flow",
    }
