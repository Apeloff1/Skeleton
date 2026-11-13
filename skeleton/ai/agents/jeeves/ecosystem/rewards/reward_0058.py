"""Reward 0058.
"""
from __future__ import annotations

REWARD = "reward_0058"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (58 % 30), "gold": 10 + (58 % 20)}
