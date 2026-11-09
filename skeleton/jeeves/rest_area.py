"""Rest and recovery areas — Pareto breathing room inside a stage.

Safe pockets after intensity so players can orient and plan.
"""

from __future__ import annotations

from typing import Any


def rest_area(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "properties": [
            "No required fail state",
            "Clear sightlines to next landmark or gate",
            "Optional examine or lore",
            "Save or checkpoint opportunity if the game has one",
        ],
        "placement": "After a high-intensity beat or before a set piece",
        "rule": "Skipping the rest area never soft-locks",
    }
