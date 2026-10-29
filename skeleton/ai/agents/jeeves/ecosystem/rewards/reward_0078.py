"""Reward 0078.
"""
from __future__ import annotations

REWARD = "reward_0078"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (78 % 30), "gold": 10 + (78 % 20)}
