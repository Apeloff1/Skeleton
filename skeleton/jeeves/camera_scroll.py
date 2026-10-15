"""Camera and scroll — Pareto framing for parallax and playfield.

Keeps the subject readable while layers move.
"""

from __future__ import annotations

from typing import Any


def camera_spec(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "follow": "lerp or exponential smoothing toward target",
        "dead_zone": "small, so micro-movement does not shake the frame",
        "look_ahead": "optional, modest, disabled if it harms puzzle readability",
        "bounds": "clamp to level; never show undefined space",
        "parallax_link": "Camera delta drives layer speeds",
        "accessibility": "Offer reduced motion that freezes or slows far layers",
    }
