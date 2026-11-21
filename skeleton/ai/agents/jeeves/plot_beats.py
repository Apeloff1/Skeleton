"""Plot beats — Pareto key story moments.

Inciting incident, midpoint, climax, resolution.

Canonical source; ``skeleton/ai/agents/jeeves/plot_beats.py`` is an exact
byte mirror governed by mapping AIFT-JEEVES.
"""

from __future__ import annotations

from typing import Any

MAX_TITLE_LENGTH = 200

BEATS: tuple[str, ...] = (
    "opening image",
    "inciting incident",
    "first plot point",
    "midpoint",
    "dark night",
    "climax",
    "resolution",
)

RULES: tuple[str, ...] = (
    "Each beat advances the central conflict",
    "Midpoint changes the direction",
    "Climax is the highest stakes",
    "Beats are visible in gameplay or dialogue",
)


def _clean_title(title: object) -> str:
    if not isinstance(title, str):
        raise TypeError("story title must be a string")
    cleaned = title.strip()
    if not cleaned:
        raise ValueError("story title must not be blank")
    if len(cleaned) > MAX_TITLE_LENGTH:
        raise ValueError(f"story title exceeds {MAX_TITLE_LENGTH} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        raise ValueError("story title must not contain control characters")
    return cleaned


def plot_beats(title: str) -> dict[str, Any]:
    """Return a fresh ordered beat sheet for ``title``."""
    return {
        "title": _clean_title(title),
        "beats": list(BEATS),
        "rules": list(RULES),
    }
