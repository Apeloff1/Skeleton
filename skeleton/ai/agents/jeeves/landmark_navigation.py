"""Landmark navigation — Pareto wayfinding inside a stage.

Distinct visual anchors so players orient without a map.
"""

from __future__ import annotations

from typing import Any


def landmark_plan(stage: str, count: int = 3) -> dict[str, Any]:
    return {
        "stage": stage,
        "landmarks": count,
        "rules": [
            "Each landmark has a unique silhouette",
            "Visible from the main path",
            "Palette or shape differs from surroundings",
            "At least one near entry and one near exit",
        ],
        "era_note": "Strong shapes over fine detail",
    }
