"""Reward 0024.
"""
from __future__ import annotations

REWARD = "reward_0024"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (24 % 30), "gold": 10 + (24 % 20)}
