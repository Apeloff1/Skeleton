"""Enemy resource pressure — Pareto tension without exhaustion.

Threats create decisions about health, ammo, or time without soft-locking.
"""

from __future__ import annotations

from typing import Any


def pressure_model() -> dict[str, Any]:
    return {
        "sources": ["health", "time", "position", "optional resources"],
        "rules": [
            "Pressure is recoverable",
            "Rest or avoid options exist on the critical path",
            "No infinite unavoidable drain",
            "Optional mastery can reduce pressure",
        ],
        "link": "Supports stage pacing highs; releases in rest areas",
    }
