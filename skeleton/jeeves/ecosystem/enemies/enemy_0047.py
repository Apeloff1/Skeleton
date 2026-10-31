"""Enemy 0047.
"""
from __future__ import annotations

ENEMY = "enemy_0047"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 47, "atk": 5 + (47 % 12), "def": 2 + (47 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
