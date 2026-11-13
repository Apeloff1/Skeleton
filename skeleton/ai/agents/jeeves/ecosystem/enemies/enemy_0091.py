"""Enemy 0091.
"""
from __future__ import annotations

ENEMY = "enemy_0091"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 91, "atk": 5 + (91 % 12), "def": 2 + (91 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
