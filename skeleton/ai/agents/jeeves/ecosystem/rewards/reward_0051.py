"""Reward 0051.
"""
from __future__ import annotations

REWARD = "reward_0051"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (51 % 30), "gold": 10 + (51 % 20)}
