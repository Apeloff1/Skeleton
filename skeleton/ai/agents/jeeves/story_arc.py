"""Story arc — Pareto three-act structure for games.

Setup, confrontation, resolution. Clear stakes and change.
"""

from __future__ import annotations

from typing import Any


def story_arc(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "acts": {
            "1_setup": "Introduce world, protagonist, ordinary world, inciting incident",
            "2_confrontation": "Rising action, complications, midpoint reversal, dark night",
            "3_resolution": "Climax, resolution, new equilibrium",
        },
        "rules": [
            "Protagonist changes by the end",
            "Stakes are clear and personal",
            "Inciting incident disrupts the status quo",
            "Midpoint raises the stakes",
            "Climax resolves the central conflict",
        ],
        "era_note": "Keep text and delivery era-appropriate",
    }
