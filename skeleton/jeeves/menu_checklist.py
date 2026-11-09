"""Menu readiness checklist — Pareto gate before menus ship.

Covers hierarchy, readability, input, feedback, settings, pause, and accessibility.
"""

from __future__ import annotations


def menu_checklist() -> list[str]:
    return [
        "Depth ≤ 3 and back is consistent",
        "Current location labeled",
        "Text high contrast and short",
        "Focus not color-only",
        "Confirm/cancel consistent",
        "Every input produces feedback",
        "Settings cover volume and reduced motion",
        "Pause freezes cleanly and resumes exactly",
        "Quit confirms",
        "No menu time pressure or soft-lock",
    ]
