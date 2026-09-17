"""Creator-lane intent compiler. Pointer clauses only. N-cap 8."""

from __future__ import annotations

import re
from typing import Any

from skeleton.game.vision_parse import parse_pointers


FIELD_HINTS = (
    ("extract", "loop"),
    ("heat", "loop"),
    ("sleep", "loop"),
    ("combat", "combat"),
    ("economy", "economy"),
    ("forge", "forge"),
    ("godot", "emit"),
    ("replay", "quality"),
)


class IntentError(ValueError):
    """Intent compiler contract violation."""


def compile_intent(vision: str | None) -> dict[str, Any]:
    blob = str(vision or "").strip()
    if not blob:
        raise IntentError("vision required")
    parsed = parse_pointers(blob)
    words = [part.lower() for part in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", blob)]
    fields: list[str] = []
    for needle, field in FIELD_HINTS:
        if needle in words and field not in fields:
            fields.append(field)
    if not fields:
        fields.append("loop")
    conflicts: list[str] = []
    if "godot" in words and "unity" in words:
        conflicts.append("emit-engine")
    return {
        "kind": "intent",
        "n": parsed["n"],
        "pointers": parsed["pointers"],
        "fields": fields,
        "conflicts": conflicts,
        "dropped": parsed["dropped"],
        "hit": parsed["hit"],
        "approval": "pending",
        "stored_prose": 0,
    }
