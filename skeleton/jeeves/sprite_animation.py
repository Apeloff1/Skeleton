"""Sprite animation — Pareto purposeful motion.

Few strong frames beat many weak ones.
"""

from __future__ import annotations

from typing import Any


def animation_set(action: str, era: str = "16bit") -> dict[str, Any]:
    return {
        "action": action,
        "era": era,
        "minimum_frames": {"idle": 2, "walk": 4, "use": 3, "hit": 2}.get(action, 2),
        "rules": [
            "Timing readable at target framerate",
            "Anticipation and follow-through where budget allows",
            "Hit or use frame is the clearest",
            "Loop cleanly if it loops",
            "Stay inside sprite and palette budget",
        ],
    }
