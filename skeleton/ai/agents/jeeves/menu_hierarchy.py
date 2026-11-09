"""Menu hierarchy — Pareto shallow, predictable navigation.

Players always know where they are and how to go back.
"""

from __future__ import annotations

from typing import Any


def hierarchy() -> dict[str, Any]:
    return {
        "max_depth": 3,
        "rules": [
            "Title → primary choices → one settings or confirm layer",
            "Back is always available and consistent",
            "Current location is labeled",
            "No orphan screens",
            "Critical actions confirm",
        ],
        "anti_pattern": "Deep nests or hidden back",
    }
