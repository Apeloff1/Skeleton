"""UI focus — Pareto clear selection state.

The active element is obvious without relying on color alone.
"""

from __future__ import annotations

from typing import Any


def focus_rules() -> dict[str, Any]:
    return {
        "indicators": ["outline", "position shift", "icon", "brightness"],
        "rules": [
            "Not color-only",
            "Visible against any background",
            "Moves with input immediately",
            "Same language in menus and in-world prompts",
        ],
    }
