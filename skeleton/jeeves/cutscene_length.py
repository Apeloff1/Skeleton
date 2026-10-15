"""Cutscene length — Pareto brevity.

Short scenes that earn their time. Prefer in-world storytelling.
"""

from __future__ import annotations

from typing import Any


def length_budget() -> dict[str, Any]:
    return {
        "target": "under 30–60 seconds unless it is the climax",
        "rules": [
            "One clear purpose per scene",
            "Cut any line that examine text could carry",
            "No repeated information",
            "Era text budget respected",
        ],
        "prefer": "Environmental or examine delivery over cutscene",
    }
