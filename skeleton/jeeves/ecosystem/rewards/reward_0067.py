"""Reward 0067.
"""
from __future__ import annotations

REWARD = "reward_0067"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (67 % 30), "gold": 10 + (67 % 20)}
