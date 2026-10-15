"""Menu input — Pareto consistent controls.

Same confirm/cancel/navigate across every screen.
"""

from __future__ import annotations

from typing import Any


def input_map(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "actions": {
            "navigate": "d-pad or stick",
            "confirm": "primary button",
            "cancel": "secondary button",
            "info": "optional, never required",
        },
        "rules": [
            "Never remap mid-menu without notice",
            "Hold-to-repeat is gentle",
            "No required rapid input",
            "Era-appropriate button count",
        ],
    }
