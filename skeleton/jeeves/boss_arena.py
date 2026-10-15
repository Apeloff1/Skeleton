"""Boss arena — Pareto readable space for the fight.

The room teaches the boundaries and hazards before they kill.
"""

from __future__ import annotations

from typing import Any


def arena(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "rules": [
            "Clear boundaries",
            "Hazards introduced with a tell",
            "Safe pockets or recovery space exist",
            "Camera or framing keeps boss and player readable",
            "No soft-lock geometry",
        ],
        "link": "Supports the boss pattern; does not hide it",
    }
