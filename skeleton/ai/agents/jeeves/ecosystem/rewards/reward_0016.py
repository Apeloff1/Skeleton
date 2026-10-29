"""Reward 0016.
"""
from __future__ import annotations

REWARD = "reward_0016"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (16 % 30), "gold": 10 + (16 % 20)}
