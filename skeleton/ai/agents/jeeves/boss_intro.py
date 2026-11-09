"""Boss intro — Pareto short establishment.

Show who and the first tell. Then give control.
"""

from __future__ import annotations

from typing import Any


def intro(name: str) -> dict[str, Any]:
    return {
        "boss": name,
        "includes": ["identity", "first tell or stance", "handoff to control"],
        "rules": [
            "Short",
            "Skippable",
            "Does not deal damage before control returns",
            "Required character info also exists in the world",
        ],
    }
