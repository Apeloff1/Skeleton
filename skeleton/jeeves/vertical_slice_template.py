"""Vertical slice template — highest-leverage production artifact.

A complete, reviewable segment of the critical path before full production.
"""

from __future__ import annotations

from typing import Any


def vertical_slice(
    title: str,
    core_verb: str = "use",
    rooms: int = 4,
    puzzles: int = 2,
) -> dict[str, Any]:
    return {
        "title": title,
        "goal": "One complete critical-path segment that proves the fantasy",
        "includes": {
            "rooms": rooms,
            "puzzles": puzzles,
            "core_verb": core_verb,
            "one_npc_or_environmental_story_beat": True,
            "save_or_flag_checkpoint": True,
            "fail_and_retry_readable": True,
        },
        "excludes": [
            "full content volume",
            "optional side areas",
            "polish beyond readability",
            "final audio/music pass",
        ],
        "acceptance": [
            "Player can start, understand verb, solve, and finish the segment",
            "No soft-lock",
            "Clue visible before each gate",
            "Era constraints respected in placeholder form",
            "Operator can review in one sitting",
        ],
        "next_after_approval": "Lock scope, expand via creation plan, or cut",
    }


def content_lock_criteria() -> list[str]:
    return [
        "No new rooms, puzzles, or critical flags",
        "All critical-path clues and hints present",
        "Asset list frozen except bugfix replacements",
        "Dialogue and examine text frozen except clarity fixes",
        "Save/flag schema frozen",
    ]
