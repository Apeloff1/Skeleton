"""Reward 0023.
"""
from __future__ import annotations

REWARD = "reward_0023"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (23 % 30), "gold": 10 + (23 % 20)}
