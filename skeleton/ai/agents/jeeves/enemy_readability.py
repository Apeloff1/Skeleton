"""Enemy readability — Pareto silhouette and state clarity.

Players must distinguish enemy type and state at a glance.
"""

from __future__ import annotations

from typing import Any


def readability(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "rules": [
            "Unique silhouette per threat type",
            "Hostile state differs from idle or stunned",
            "High contrast against playfield and parallax",
            "Attack wind-up uses a distinct pose",
            "Palette stays inside era limits",
        ],
        "test": "Squint or distance test — type and danger still readable",
    }
