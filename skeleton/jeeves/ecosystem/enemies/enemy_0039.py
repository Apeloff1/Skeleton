"""Enemy 0039.
"""
from __future__ import annotations

ENEMY = "enemy_0039"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 39, "atk": 5 + (39 % 12), "def": 2 + (39 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
