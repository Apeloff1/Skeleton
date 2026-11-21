"""Story arc — Pareto three-act structure for games.

Setup, confrontation, resolution. Clear stakes and change.

Canonical source; ``skeleton/ai/agents/jeeves/story_arc.py`` is an exact
byte mirror governed by mapping AIFT-JEEVES.
"""

from __future__ import annotations

from typing import Any

MAX_TITLE_LENGTH = 200

ACTS: tuple[tuple[str, str], ...] = (
    ("1_setup", "Introduce world, protagonist, ordinary world, inciting incident"),
    ("2_confrontation", "Rising action, complications, midpoint reversal, dark night"),
    ("3_resolution", "Climax, resolution, new equilibrium"),
)

RULES: tuple[str, ...] = (
    "Protagonist changes by the end",
    "Stakes are clear and personal",
    "Inciting incident disrupts the status quo",
    "Midpoint raises the stakes",
    "Climax resolves the central conflict",
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


def story_arc(title: str) -> dict[str, Any]:
    """Return a fresh three-act outline for ``title``.

    Each call returns new containers, so callers may annotate the outline
    without mutating shared module state.
    """
    return {
        "title": _clean_title(title),
        "acts": dict(ACTS),
        "rules": list(RULES),
        "era_note": "Keep text and delivery era-appropriate",
    }
