"""Questions worth asking before a build, derived from what the compiler guessed."""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.forge.game_design_spec import _GENRES  # closed vocabulary


def clarifying_questions(brief: str, spec: Mapping[str, Any]) -> list[dict[str, str]]:
    lowered = brief.casefold()
    out: list[dict[str, str]] = []
    if not any(stem in lowered for _, stems in _GENRES for stem in stems):
        out.append({"field": "genre", "question": "Which genre: top-down shooter, platformer, or roguelike RPG?",
                    "default": str(spec.get("genre", ""))})
    if "fantasy:" not in lowered:
        out.append({"field": "fantasy", "question": "What is the setting or fantasy in one line?",
                    "default": str(spec.get("fantasy", ""))})
    if "core loop:" not in lowered:
        out.append({"field": "core_loop", "question": "What does the player repeat each minute?",
                    "default": str(spec.get("core_loop", ""))})
    return out
