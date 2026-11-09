"""Sprite budget — Pareto hardware limits.

Count, size, and colors stay inside the target core.
"""

from __future__ import annotations

from typing import Any


def sprite_budget(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "track": ["on-screen count", "size in pixels", "colors per sprite", "animation frames"],
        "rules": [
            "Design to the limit, not past it",
            "Reuse frames and palette where possible",
            "UI sprites counted in the same budget if they share the layer",
            "Document the budget in the asset catalog",
        ],
        "overflow": "Cut flourish before cutting readability",
    }
