"""Enemy 0077.
"""
from __future__ import annotations

ENEMY = "enemy_0077"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 77, "atk": 5 + (77 % 12), "def": 2 + (77 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
