"""Parallax readiness checklist — Pareto gate before using depth.

Combines layer, camera, readability, budget, and comfort checks.
"""

from __future__ import annotations


def parallax_checklist() -> list[str]:
    return [
        "Layer count within era limit",
        "Speeds decrease with distance",
        "Playfield higher contrast than far layers",
        "Interactive elements not on far/near decorative layers",
        "Depth sort prevents pop-through",
        "Camera bounds and dead zone set",
        "VFX within budget",
        "Reduced-motion option defined",
        "Provenance recorded for each layer",
        "Squint test and short comfort pass done",
    ]
