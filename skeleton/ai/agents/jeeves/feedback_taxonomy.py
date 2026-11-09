"""Feedback taxonomy — Pareto clarity for every player action.

Every verb needs readable success, fail, and progress signals.
"""

from __future__ import annotations

from typing import Any


def feedback_spec(verb: str) -> dict[str, Any]:
    return {
        "verb": verb,
        "success": "immediate visual + audio + optional short text",
        "fail": "readable reason, no silent rejection",
        "progress": "state change visible in world or inventory",
        "latency": "same frame or next frame where hardware allows",
        "era_note": "Keep signals within palette, sprite, and audio limits",
    }


def taxonomy() -> list[str]:
    return [
        "confirm (action accepted)",
        "reject (action invalid + why)",
        "progress (partial advance)",
        "complete (puzzle/flag set)",
        "danger (upcoming fail or cost)",
        "reward (mastery or discovery)",
    ]
