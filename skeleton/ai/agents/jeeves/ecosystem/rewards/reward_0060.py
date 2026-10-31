"""Reward 0060.
"""
from __future__ import annotations

REWARD = "reward_0060"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (60 % 30), "gold": 10 + (60 % 20)}
