"""Sprite reuse — Pareto efficiency inside budget.

Share frames, palettes, and rigs before adding new art.
"""

from __future__ import annotations

from typing import Any


def reuse_policy() -> dict[str, Any]:
    return {
        "prefer": [
            "shared walk cycles where silhouette allows",
            "palette swaps that preserve readability",
            "modular props",
            "mirrored frames when the action is symmetric",
        ],
        "avoid": [
            "unique art for one-off that could be a variant",
            "palette swap that breaks silhouette or material read",
        ],
        "gain": "Stays inside sprite and time budget",
    }
