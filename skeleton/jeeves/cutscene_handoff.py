"""Cutscene handoff — Pareto return to player control.

The scene ends by giving the player a clear next action.
"""

from __future__ import annotations

from typing import Any


def handoff() -> dict[str, Any]:
    return {
        "ends_with": ["gameplay control", "or a menu the player expects"],
        "rules": [
            "Player position and state are sensible",
            "Next verb or path is clued",
            "No progress lost",
            "Flags set by the scene are visible in the world",
        ],
    }
