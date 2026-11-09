"""Cutscene readability — Pareto clear staging and text.

Who is acting and what changed must be obvious.
"""

from __future__ import annotations

from typing import Any


def readability() -> dict[str, Any]:
    return {
        "rules": [
            "Speaker identifiable",
            "Text high contrast and short",
            "Important action staged in clear silhouette",
            "No essential info in a single fast frame",
            "Era palette and sprite limits respected",
        ],
        "test": "Viewer can retell the beat after one viewing",
    }
