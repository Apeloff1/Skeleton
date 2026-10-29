"""Reward 0049.
"""
from __future__ import annotations

REWARD = "reward_0049"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (49 % 30), "gold": 10 + (49 % 20)}
