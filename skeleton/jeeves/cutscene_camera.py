"""Cutscene camera — Pareto framing that serves the beat.

Stable, readable, era-appropriate. No motion for its own sake.
"""

from __future__ import annotations

from typing import Any


def camera() -> dict[str, Any]:
    return {
        "rules": [
            "Subject stays in frame and readable",
            "Cuts motivated by the beat",
            "Motion comfort rules apply",
            "No essential detail at the edge",
            "Reduced-motion alternative if the scene relies on big moves",
        ],
    }
