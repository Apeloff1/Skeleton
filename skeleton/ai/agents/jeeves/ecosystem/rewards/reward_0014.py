"""Reward 0014.
"""
from __future__ import annotations

REWARD = "reward_0014"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (14 % 30), "gold": 10 + (14 % 20)}
