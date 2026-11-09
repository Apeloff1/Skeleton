"""Reward 0061.
"""
from __future__ import annotations

REWARD = "reward_0061"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (61 % 30), "gold": 10 + (61 % 20)}
