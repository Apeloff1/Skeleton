"""Enemy placement — Pareto positioning inside a stage.

Threats support the stage flow instead of ambushing unfairly.
"""

from __future__ import annotations

from typing import Any


def placement_rules() -> dict[str, Any]:
    return {
        "rules": [
            "First of a type appears in a low-pressure space",
            "Never spawn directly on the player",
            "Sightlines or audio hint before a dangerous room",
            "Rest areas stay safe",
            "Optional branches may hold tougher variants",
        ],
        "link": "Align with stage pacing highs and set pieces",
    }
