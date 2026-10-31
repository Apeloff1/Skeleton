"""Enemy 0032.
"""
from __future__ import annotations

ENEMY = "enemy_0032"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 32, "atk": 5 + (32 % 12), "def": 2 + (32 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
