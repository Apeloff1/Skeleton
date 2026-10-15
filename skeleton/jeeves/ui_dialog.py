"""Dialogue UI — Pareto readable conversation without blocking the world longer than needed.

Speaker, text, and choices stay clear and skippable where fair.
"""

from __future__ import annotations

from typing import Any


def dialogue_ui() -> dict[str, Any]:
    return {
        "shows": ["speaker", "short text", "choices if any"],
        "rules": [
            "Text fits era screen",
            "Advance is explicit",
            "Choices are readable and selectable",
            "Can review last line if budget allows",
            "Does not soft-lock",
        ],
    }
