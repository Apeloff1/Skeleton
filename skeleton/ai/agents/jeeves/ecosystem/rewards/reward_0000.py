"""Reward 0000.
"""
from __future__ import annotations

REWARD = "reward_0000"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (0 % 30), "gold": 10 + (0 % 20)}
