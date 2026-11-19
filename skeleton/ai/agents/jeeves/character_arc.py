"""Character arc — Pareto internal change.

Want vs need. Flaw to growth or tragic fall.
"""

from __future__ import annotations

from typing import Any


def character_arc(name: str) -> dict[str, Any]:
    return {
        "character": name,
        "elements": {
            "want": "External goal",
            "need": "Internal lesson",
            "flaw": "What blocks the need",
            "ghost": "Past event shaping the flaw",
            "change": "How they grow or fail",
        },
        "rules": [
            "Arc intersects with plot",
            "Change is earned through events",
            "Supporting characters have lighter arcs",
            "No orphan protagonists",
        ],
    }
