"""Menu accessibility — Pareto inclusive defaults.

Focus, contrast, and motion options that do not break the era fantasy.
"""

from __future__ import annotations

from typing import Any


def accessibility() -> dict[str, Any]:
    return {
        "minimum": [
            "Focus not color-only",
            "High contrast text",
            "Reduced motion option for transitions",
            "No time pressure on menus",
        ],
        "rules": [
            "Defaults are usable",
            "Options persist",
            "Do not require fine timing",
        ],
    }
