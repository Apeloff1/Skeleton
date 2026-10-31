"""Enemy 0043.
"""
from __future__ import annotations

ENEMY = "enemy_0043"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 43, "atk": 5 + (43 % 12), "def": 2 + (43 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
