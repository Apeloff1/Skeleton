"""Motion comfort — Pareto safety for parallax and camera.

Depth should not cause discomfort.
"""

from __future__ import annotations

from typing import Any


def motion_rules() -> dict[str, Any]:
    return {
        "max_relative_speed": "far layers noticeably slower than playfield",
        "avoid": ["rapid full-screen strobe", "conflicting motion directions", "high-amplitude shake on puzzle screens"],
        "reduced_motion": "freeze or greatly slow far layers; keep playfield stable",
        "test": "short session on target hardware or core; note any discomfort",
    }
