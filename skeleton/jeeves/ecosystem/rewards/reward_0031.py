"""Reward 0031.
"""
from __future__ import annotations

REWARD = "reward_0031"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (31 % 30), "gold": 10 + (31 % 20)}
