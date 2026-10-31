"""Reward 0089.
"""
from __future__ import annotations

REWARD = "reward_0089"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (89 % 30), "gold": 10 + (89 % 20)}
