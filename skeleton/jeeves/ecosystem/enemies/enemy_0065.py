"""Enemy 0065.
"""
from __future__ import annotations

ENEMY = "enemy_0065"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 65, "atk": 5 + (65 % 12), "def": 2 + (65 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
