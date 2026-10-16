"""Boss tells — Pareto unique wind-ups per attack.

Each dangerous move has a distinct, learnable anticipation.
"""

from __future__ import annotations

from typing import Any


def tells(attacks: list[str]) -> dict[str, Any]:
    return {
        "attacks": attacks,
        "rules": [
            "Unique pose or effect per attack",
            "Timing reactable on target hardware",
            "Audio support if budget allows",
            "Tell differs from idle and from other attacks",
            "First use may be slower",
        ],
    }
