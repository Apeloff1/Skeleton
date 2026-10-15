"""Boss design — Pareto climactic enemy that reuses taught verbs.

A boss is a stage set piece with phases, not a new unexplained system.
"""

from __future__ import annotations

from typing import Any


def boss(name: str, phases: int = 2) -> dict[str, Any]:
    return {
        "name": name,
        "phases": phases,
        "rules": [
            "Each phase telegraphs",
            "Core verb from the game remains the answer",
            "Phase change is readable",
            "Recovery windows exist",
            "Failure returns to a fair retry",
        ],
        "anti_pattern": "New required mechanic introduced only in the boss with no teach",
    }
