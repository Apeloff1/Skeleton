"""Reward 0087.
"""
from __future__ import annotations

REWARD = "reward_0087"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (87 % 30), "gold": 10 + (87 % 20)}
