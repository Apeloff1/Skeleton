"""Enemy 0045.
"""
from __future__ import annotations

ENEMY = "enemy_0045"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 45, "atk": 5 + (45 % 12), "def": 2 + (45 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
