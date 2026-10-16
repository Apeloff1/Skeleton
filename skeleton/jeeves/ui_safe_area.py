"""UI safe area — Pareto placement that survives hardware framing.

Keep essential UI inside the visible, high-contrast region.
"""

from __future__ import annotations

from typing import Any


def safe_area(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "rules": [
            "Essential UI inset from edges",
            "Account for overscan on era displays",
            "Playfield center stays clear",
            "Test on target core or reference frame",
        ],
    }
