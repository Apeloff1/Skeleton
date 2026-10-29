"""Reward 0097.
"""
from __future__ import annotations

REWARD = "reward_0097"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (97 % 30), "gold": 10 + (97 % 20)}
