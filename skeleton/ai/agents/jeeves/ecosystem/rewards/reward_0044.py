"""Reward 0044.
"""
from __future__ import annotations

REWARD = "reward_0044"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (44 % 30), "gold": 10 + (44 % 20)}
