"""Canonical GameForge questionnaire. Free-form vision maps into fields."""

from __future__ import annotations

import re
from typing import Any, Mapping

from skeleton.game.intent import compile_intent
from skeleton.game.spec import compile_spec


CANON = (
    "loop",
    "combat",
    "economy",
    "progression",
    "ai",
    "world",
    "emit",
    "quality",
)
HINTS = (
    ("extract", "loop"),
    ("heat", "loop"),
    ("sleep", "loop"),
    ("dream", "loop"),
    ("combat", "combat"),
    ("attack", "combat"),
    ("scrap", "economy"),
    ("craft", "economy"),
    ("level", "progression"),
    ("xp", "progression"),
    ("stalker", "ai"),
    ("patrol", "ai"),
    ("room", "world"),
    ("door", "world"),
    ("godot", "emit"),
    ("replay", "quality"),
)


class QuestionnaireError(ValueError):
    """Questionnaire contract violation."""


def _words(blob: str) -> list[str]:
    return [part.lower() for part in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", blob)]


def fill(vision: str, answers: Mapping[str, Any] | None = None) -> dict[str, Any]:
    blob = str(vision or "").strip()
    if not blob:
        raise QuestionnaireError("vision required")
    intent = compile_intent(blob)
    spec = compile_spec(blob)
    raw = {str(key): value for key, value in dict(answers or {}).items()}
    words = _words(blob)
    mapped: dict[str, int] = {field: 0 for field in CANON}
    for needle, field in HINTS:
        if needle in words:
            mapped[field] = 1
    for field in CANON:
        if field in intent["fields"] or field in spec["fields"] or raw.get(field):
            mapped[field] = 1
    if not any(mapped.values()):
        mapped["loop"] = 1
    conflicts = list(spec["conflicts"])
    if mapped["emit"] and "unity" in words:
        if "emit-engine" not in conflicts:
            conflicts.append("emit-engine")
    missing = [field for field, hit in mapped.items() if not hit]
    return {
        "kind": "questionnaire",
        "fields": mapped,
        "filled": [field for field, hit in mapped.items() if hit],
        "missing": missing,
        "conflicts": conflicts,
        "intent_n": intent["n"],
        "stored_prose": 0,
        "ok": True,
    }
