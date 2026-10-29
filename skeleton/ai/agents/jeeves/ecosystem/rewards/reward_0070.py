"""Reward 0070.
"""
from __future__ import annotations

REWARD = "reward_0070"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (70 % 30), "gold": 10 + (70 % 20)}
