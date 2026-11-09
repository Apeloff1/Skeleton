"""Sprite palette — Pareto color limits per era.

Fewer, purposeful colors beat noisy palettes.
"""

from __future__ import annotations

from typing import Any


def palette_budget(era: str = "16bit") -> dict[str, Any]:
    budgets = {
        "8bit": "very small, high contrast",
        "16bit": "constrained per sprite or tile",
        "handheld": "small, readable on dim screens",
        "32bit": "broader but still disciplined",
    }
    return {
        "era": era,
        "budget": budgets.get(era, "respect core limits"),
        "rules": [
            "Reserve brightest values for focus or interactive",
            "Consistent material colors across a character",
            "No palette swap that destroys silhouette",
            "Provenance notes the source palette",
        ],
    }
