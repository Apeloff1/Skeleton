"""Character arc — Pareto internal change.

Want vs need. Flaw to growth or tragic fall.

Canonical source; ``skeleton/ai/agents/jeeves/character_arc.py`` is an exact
byte mirror governed by mapping AIFT-JEEVES.
"""

from __future__ import annotations

from typing import Any

MAX_NAME_LENGTH = 120

ELEMENTS: tuple[tuple[str, str], ...] = (
    ("want", "External goal"),
    ("need", "Internal lesson"),
    ("flaw", "What blocks the need"),
    ("ghost", "Past event shaping the flaw"),
    ("change", "How they grow or fail"),
)

RULES: tuple[str, ...] = (
    "Arc intersects with plot",
    "Change is earned through events",
    "Supporting characters have lighter arcs",
    "No orphan protagonists",
)


def _clean_name(name: object) -> str:
    if not isinstance(name, str):
        raise TypeError("character name must be a string")
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("character name must not be blank")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValueError(f"character name exceeds {MAX_NAME_LENGTH} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        raise ValueError("character name must not contain control characters")
    return cleaned


def character_arc(name: str) -> dict[str, Any]:
    """Return a fresh want/need/flaw/ghost/change outline for ``name``.

    Each call returns new containers, so callers may annotate the outline
    without mutating shared module state.
    """
    return {
        "character": _clean_name(name),
        "elements": dict(ELEMENTS),
        "rules": list(RULES),
    }
