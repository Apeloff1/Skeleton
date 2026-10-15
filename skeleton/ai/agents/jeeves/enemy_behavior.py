"""Enemy behavior — Pareto simple, readable state machines.

Prefer few clear states over opaque complexity.
"""

from __future__ import annotations

from typing import Any


def behavior_machine(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "states": ["idle", "alert", "telegraph", "act", "recover", "stunned"],
        "rules": [
            "Transitions are visible",
            "Alert has a range or trigger the player can learn",
            "Act is always preceded by telegraph unless purely passive",
            "Stunned or recover gives a punish window",
        ],
        "determinism": "Same inputs produce same reactions where possible",
    }
