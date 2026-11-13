"""Reward 0003.
"""
from __future__ import annotations

REWARD = "reward_0003"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (3 % 30), "gold": 10 + (3 % 20)}
