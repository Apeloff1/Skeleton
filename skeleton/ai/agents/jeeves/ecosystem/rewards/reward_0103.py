"""Reward 0103.
"""
from __future__ import annotations

REWARD = "reward_0103"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (103 % 30), "gold": 10 + (103 % 20)}
