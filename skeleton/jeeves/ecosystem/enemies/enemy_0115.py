"""Enemy 0115.
"""
from __future__ import annotations

ENEMY = "enemy_0115"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 115, "atk": 5 + (115 % 12), "def": 2 + (115 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
