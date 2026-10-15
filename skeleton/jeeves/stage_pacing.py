"""Stage pacing — Pareto rhythm inside one stage.

Alternates tension and release so the stage does not flatten or exhaust.
"""

from __future__ import annotations

from typing import Any


def pacing_map(beats: int = 6) -> dict[str, Any]:
    pattern = ["low", "rise", "high", "release", "rise", "resolve"]
    return {
        "beats": beats,
        "intensity": (pattern * ((beats // 6) + 1))[:beats],
        "rules": [
            "No two highs without a release",
            "Teach beats stay low-intensity",
            "Final beat resolves or clearly hands off",
        ],
    }
