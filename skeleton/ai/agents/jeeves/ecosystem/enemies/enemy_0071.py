"""Enemy 0071.
"""
from __future__ import annotations

ENEMY = "enemy_0071"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 71, "atk": 5 + (71 % 12), "def": 2 + (71 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
