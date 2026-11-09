"""Boss openings — Pareto punish windows.

After an attack or phase, the player gets a clear chance to respond.
"""

from __future__ import annotations

from typing import Any


def openings() -> dict[str, Any]:
    return {
        "rules": [
            "Every major attack has a recovery",
            "Recovery is visually distinct",
            "Window long enough for the core verb",
            "Missing the window is not fatal on first tries",
            "Openings shrink only after the pattern is taught",
        ],
    }
