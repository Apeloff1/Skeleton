"""Reward 0118.
"""
from __future__ import annotations

REWARD = "reward_0118"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (118 % 30), "gold": 10 + (118 % 20)}
