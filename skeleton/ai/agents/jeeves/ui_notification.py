"""UI notifications — Pareto brief, non-blocking signals.

Item get, flag set, or warning. Then disappear.
"""

from __future__ import annotations

from typing import Any


def notification() -> dict[str, Any]:
    return {
        "types": ["item", "flag", "warning", "objective update"],
        "rules": [
            "Short",
            "Non-blocking",
            "Auto-dismiss",
            "Does not cover critical playfield",
            "Logged if the player might need it later",
        ],
    }
