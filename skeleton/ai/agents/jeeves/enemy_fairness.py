"""Enemy fairness — Pareto rules so threats teach rather than punish blindly.

Damage is avoidable once the pattern is known.
"""

from __future__ import annotations

from typing import Any


def fairness_rules() -> dict[str, Any]:
    return {
        "rules": [
            "First encounter teaches the pattern",
            "Damage is avoidable after the teach",
            "No unavoidable damage in a rest area",
            "Failure feedback explains the miss",
            "Critical path never requires perfect play on first try",
        ],
        "measure": "Playtest: player succeeds on retry without external guide",
    }
