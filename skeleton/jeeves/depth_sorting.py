"""Depth sorting — Pareto draw order for layered scenes.

Y-sort or explicit layers so characters and props read correctly against parallax.
"""

from __future__ import annotations

from typing import Any


def depth_rules(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "method": "y-sort for ground actors; explicit layer for UI and far parallax",
        "rules": [
            "Actors on the same ground plane sort by baseline Y",
            "Far parallax never sorts in front of playfield",
            "UI always above world",
            "Respect sprite limit — prefer layer reuse over extra sprites",
        ],
        "fail_modes": ["character pop-through", "hotspot hidden behind decor", "UI under world"],
    }
