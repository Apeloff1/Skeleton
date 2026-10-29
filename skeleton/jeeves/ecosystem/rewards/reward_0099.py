"""Reward 0099.
"""
from __future__ import annotations

REWARD = "reward_0099"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (99 % 30), "gold": 10 + (99 % 20)}
