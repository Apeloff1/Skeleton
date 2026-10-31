"""Enemy 0082.
"""
from __future__ import annotations

ENEMY = "enemy_0082"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 82, "atk": 5 + (82 % 12), "def": 2 + (82 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
