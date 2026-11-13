"""Enemy 0085.
"""
from __future__ import annotations

ENEMY = "enemy_0085"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 85, "atk": 5 + (85 % 12), "def": 2 + (85 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
