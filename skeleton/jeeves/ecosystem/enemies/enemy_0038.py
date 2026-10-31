"""Enemy 0038.
"""
from __future__ import annotations

ENEMY = "enemy_0038"

def combat_stats() -> dict:
    return {"id": ENEMY, "hp": 30 + 38, "atk": 5 + (38 % 12), "def": 2 + (38 % 8)}

def aggro(distance: float) -> bool:
    return distance < 8.0
