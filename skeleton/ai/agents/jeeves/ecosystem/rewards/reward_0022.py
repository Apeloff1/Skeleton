"""Reward 0022.
"""
from __future__ import annotations

REWARD = "reward_0022"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (22 % 30), "gold": 10 + (22 % 20)}
