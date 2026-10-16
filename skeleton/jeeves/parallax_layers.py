"""Parallax layer system — Pareto depth for era-constrained games.

Multiple background layers scrolling at different rates.
Respects hardware limits (layer count, palette, sprite budget).
"""

from __future__ import annotations

from typing import Any


def parallax_setup(era: str = "16bit", layers: int = 3) -> dict[str, Any]:
    max_layers = {"8bit": 1, "handheld": 2, "16bit": 3, "32bit": 5}.get(era, 3)
    count = min(layers, max_layers)
    return {
        "era": era,
        "layers": count,
        "speeds": [0.2, 0.5, 1.0][:count],  # far to near
        "rules": [
            "Far layers move slower",
            "Nearest layer may hold interactive hotspots",
            "Stay inside palette and layer limits of the era",
            "No parallax if it harms readability of the playfield",
        ],
        "budget": "Count toward background layer limit, not sprite limit",
    }


def readability_check() -> list[str]:
    return [
        "Playfield remains high-contrast against all layers",
        "Interactive elements never blend into parallax",
        "Motion does not induce discomfort at target framerate",
        "Works with reduced motion if accessibility is in scope",
    ]
