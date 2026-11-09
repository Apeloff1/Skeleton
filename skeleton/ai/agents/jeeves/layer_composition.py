"""Layer composition — Pareto assembly order for parallax scenes.

Defines the stack so artists and designers share one mental model.
"""

from __future__ import annotations

from typing import Any


def composition_stack(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "bottom_to_top": [
            "far parallax",
            "mid parallax",
            "playfield / ground",
            "actors and props (y-sorted)",
            "near foreground (optional, non-interactive or clearly so)",
            "VFX",
            "UI",
        ],
        "rule": "Interactive elements live on playfield or actor layers only",
        "export": "Each layer named and provenance-tracked",
    }
