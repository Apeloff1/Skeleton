"""Reward 0018.
"""
from __future__ import annotations

REWARD = "reward_0018"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (18 % 30), "gold": 10 + (18 % 20)}
