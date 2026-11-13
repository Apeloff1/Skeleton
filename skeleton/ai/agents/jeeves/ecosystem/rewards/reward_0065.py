"""Reward 0065.
"""
from __future__ import annotations

REWARD = "reward_0065"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (65 % 30), "gold": 10 + (65 % 20)}
