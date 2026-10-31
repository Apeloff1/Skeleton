"""Faction 038.
"""
from __future__ import annotations

FACTION = "faction_038"
ALIGNMENT = ["order", "chaos", "neutral"][38 % 3]

def relation(other: str) -> float:
    if not other:
        return 0.0
    return round(0.2 + (38 % 5) * 0.15, 2)

def roster() -> list[str]:
    return [f"{FACTION}_grunt", f"{FACTION}_elite", f"{FACTION}_leader"]
