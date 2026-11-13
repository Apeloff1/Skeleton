"""Faction 015.
"""
from __future__ import annotations

FACTION = "faction_015"
ALIGNMENT = ["order", "chaos", "neutral"][15 % 3]

def relation(other: str) -> float:
    if not other:
        return 0.0
    return round(0.2 + (15 % 5) * 0.15, 2)

def roster() -> list[str]:
    return [f"{FACTION}_grunt", f"{FACTION}_elite", f"{FACTION}_leader"]
