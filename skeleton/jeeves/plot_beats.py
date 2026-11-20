"""Plot beats — Pareto key story moments.

Inciting incident, midpoint, climax, resolution.
"""

from __future__ import annotations

from typing import Any


def plot_beats(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "beats": [
            "opening image",
            "inciting incident",
            "first plot point",
            "midpoint",
            "dark night",
            "climax",
            "resolution",
        ],
        "rules": [
            "Each beat advances the central conflict",
            "Midpoint changes the direction",
            "Climax is the highest stakes",
            "Beats are visible in gameplay or dialogue",
        ],
    }
