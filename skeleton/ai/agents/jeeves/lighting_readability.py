"""Lighting and readability — Pareto contrast for layered scenes.

Parallax and depth only work if the playfield stays readable.
"""

from __future__ import annotations

from typing import Any


def lighting_rules(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "direction": "consistent key light across a scene",
        "contrast": "playfield and hotspots higher contrast than far layers",
        "palette": "reserve brightest values for interactive or important elements",
        "fog_or_fade": "use only if era supports and readability holds",
        "check": "Squint test — subject still readable",
    }
