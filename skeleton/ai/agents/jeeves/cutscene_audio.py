"""Cutscene audio — Pareto support, not competition.

Music and stingers underline the beat. Dialogue stays intelligible.
"""

from __future__ import annotations

from typing import Any


def audio() -> dict[str, Any]:
    return {
        "rules": [
            "Dialogue or text has priority over music",
            "Stingers mark turns, not every line",
            "Era instrumentation",
            "No clipping",
            "Skip cuts audio cleanly",
        ],
    }
