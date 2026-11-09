"""Sprite silhouette — Pareto readability at native resolution.

Shape must read before color or detail.
"""

from __future__ import annotations

from typing import Any


def silhouette_rules(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "rules": [
            "Distinct outline per character or prop type",
            "Readable at 1x native scale",
            "Key pose recognizable in one frame",
            "Avoid thin features that vanish when scaled or on hardware",
            "Contrast against typical backgrounds",
        ],
        "test": "Black-only version still identifiable",
    }
