"""Enemy 0062.
"""
from __future__ import annotations

ENEMY = "enemy_0062"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 62, "atk": 5 + (62 % 12), "def": 2 + (62 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
