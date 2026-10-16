"""HUD minimalism — Pareto only what the player needs in the moment.

Health, objective, or verb hint. Nothing that covers the playfield.
"""

from __future__ import annotations

from typing import Any


def hud_spec(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "show": ["critical resource", "current objective or verb if unclear"],
        "hide": ["full inventory", "lore", "detailed map unless requested"],
        "rules": [
            "Never obscure interactive hotspots or enemies",
            "High contrast",
            "Collapses or fades when not needed",
            "Era-appropriate size",
        ],
    }
