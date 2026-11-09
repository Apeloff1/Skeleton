"""Reward 0083.
"""
from __future__ import annotations

REWARD = "reward_0083"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (83 % 30), "gold": 10 + (83 % 20)}
