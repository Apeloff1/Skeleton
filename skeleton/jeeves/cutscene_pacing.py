"""Cutscene pacing — Pareto rhythm inside a scene.

Setup, turn, button. No dead air.
"""

from __future__ import annotations

from typing import Any


def pacing() -> dict[str, Any]:
    return {
        "beats": ["establish", "turn", "button"],
        "rules": [
            "Each beat advances information or emotion",
            "No repeated pose without purpose",
            "Text advance waits for the player or uses a fair auto with skip",
            "Ends on a clear handoff to gameplay",
        ],
    }
