"""Enemy 0061.
"""
from __future__ import annotations

ENEMY = "enemy_0061"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 61, "atk": 5 + (61 % 12), "def": 2 + (61 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
