"""Faction 023.
"""
from __future__ import annotations

FACTION = "faction_023"
ALIGNMENT = ["order", "chaos", "neutral"][23 % 3]

def relation(other: str) -> float:
    if not other:
        return 0.0
    return round(0.2 + (23 % 5) * 0.15, 2)

def roster() -> list[str]:
    return [f"{FACTION}_grunt", f"{FACTION}_elite", f"{FACTION}_leader"]
