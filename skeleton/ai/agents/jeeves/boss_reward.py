"""Boss reward — Pareto clear payoff.

Victory gives a readable reward and a clean exit from the arena.
"""

from __future__ import annotations

from typing import Any


def reward() -> dict[str, Any]:
    return {
        "includes": ["victory beat", "reward or path forward", "state update"],
        "rules": [
            "Reward is visible and explained by examine or short text",
            "Critical path advances",
            "Optional mastery rewards stay optional",
            "Exit from arena is obvious",
        ],
    }
