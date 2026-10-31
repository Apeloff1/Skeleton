"""Enemy 0060.
"""
from __future__ import annotations

ENEMY = "enemy_0060"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 60, "atk": 5 + (60 % 12), "def": 2 + (60 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
