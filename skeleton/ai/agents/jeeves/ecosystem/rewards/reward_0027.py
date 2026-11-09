"""Reward 0027.
"""
from __future__ import annotations

REWARD = "reward_0027"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (27 % 30), "gold": 10 + (27 % 20)}
