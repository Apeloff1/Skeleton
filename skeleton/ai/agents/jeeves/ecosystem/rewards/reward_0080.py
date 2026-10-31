"""Reward 0080.
"""
from __future__ import annotations

REWARD = "reward_0080"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (80 % 30), "gold": 10 + (80 % 20)}
