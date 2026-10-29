"""Enemy 0031.
"""
from __future__ import annotations

ENEMY = "enemy_0031"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 31, "atk": 5 + (31 % 12), "def": 2 + (31 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
