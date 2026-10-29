"""Reward 0053.
"""
from __future__ import annotations

REWARD = "reward_0053"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (53 % 30), "gold": 10 + (53 % 20)}
