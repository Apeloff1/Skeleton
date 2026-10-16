"""Sprite states — Pareto visual language for game state.

Idle, move, act, hurt, and special must be distinguishable.
"""

from __future__ import annotations

from typing import Any


def state_set() -> dict[str, Any]:
    return {
        "required": ["idle", "move", "act", "hurt"],
        "optional": ["special", "victory", "defeat"],
        "rules": [
            "Each required state has a unique key pose",
            "Hurt is immediately readable",
            "Act frame communicates the verb",
            "Transitions do not hide the state",
        ],
    }
