"""VFX budget — Pareto limits for juice in era-constrained games.

Effects must not steal from playfield readability or sprite limits.
"""

from __future__ import annotations

from typing import Any


def vfx_budget(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "priority": ["interaction feedback", "state change", "optional flourish"],
        "limits": {
            "8bit": "minimal flash or palette cycle",
            "16bit": "short sprite or layer effects",
            "handheld": "very short, high-contrast",
            "32bit": "richer but still budgeted",
        }.get(era, "budgeted"),
        "rule": "If VFX harms readability or exceeds sprite/layer budget, cut it",
    }
