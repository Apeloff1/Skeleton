"""Enemy 0067.
"""
from __future__ import annotations

ENEMY = "enemy_0067"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 67, "atk": 5 + (67 % 12), "def": 2 + (67 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
