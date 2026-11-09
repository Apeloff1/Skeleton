"""Boss phases — Pareto readable escalation.

Each phase changes the pattern in a way the player can see and learn.
"""

from __future__ import annotations

from typing import Any


def phases(name: str, count: int = 3) -> dict[str, Any]:
    return {
        "boss": name,
        "count": count,
        "rules": [
            "Phase change is telegraphed",
            "New pattern reuses a taught verb or clearly extends it",
            "Health or stagger threshold is readable",
            "Recovery window exists between phases",
            "No sudden unavoidable damage on transition",
        ],
    }
