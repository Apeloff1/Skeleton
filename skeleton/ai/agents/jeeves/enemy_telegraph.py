"""Enemy telegraph — Pareto fairness for attacks.

Every dangerous action has a readable wind-up.
"""

from __future__ import annotations

from typing import Any


def telegraph(attack: str, era: str = "16bit") -> dict[str, Any]:
    return {
        "attack": attack,
        "era": era,
        "requirements": [
            "Distinct anticipation pose or effect",
            "Timing long enough to react on target hardware",
            "Audio cue if palette/sprite budget allows",
            "Recovery after the attack",
        ],
        "anti_patterns": ["instant hit with no tell", "tell identical to idle"],
        "test": "Player can identify the attack before it connects",
    }
