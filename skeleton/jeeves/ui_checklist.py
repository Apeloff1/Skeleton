"""UI readiness checklist — Pareto gate before in-game UI ships.

Covers HUD, focus, prompts, inventory, dialogue, notifications, and safe area.
"""

from __future__ import annotations


def ui_checklist() -> list[str]:
    return [
        "HUD shows only critical info",
        "Nothing essential is color-only",
        "Focus state is obvious",
        "Prompts do not cover hotspots and fade after teach",
        "Inventory open/close is safe",
        "Dialogue is short and advance is explicit",
        "Notifications are non-blocking",
        "Essential UI is inside the safe area",
        "Playfield center stays readable",
        "Era palette and sprite budget respected",
    ]
