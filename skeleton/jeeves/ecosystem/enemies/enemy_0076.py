"""Enemy 0076.
"""
from __future__ import annotations

ENEMY = "enemy_0076"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 76, "atk": 5 + (76 % 12), "def": 2 + (76 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
