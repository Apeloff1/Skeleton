"""Pause menu — Pareto safe interrupt.

Opening pause never loses progress or creates a soft-lock.
"""

from __future__ import annotations

from typing import Any


def pause_spec() -> dict[str, Any]:
    return {
        "includes": ["resume", "settings", "quit to title (confirm)"],
        "rules": [
            "Game state freezes cleanly",
            "Resume returns to exact prior state",
            "Quit confirms",
            "No required action inside pause to avoid soft-lock",
            "Readable over any background",
        ],
    }
