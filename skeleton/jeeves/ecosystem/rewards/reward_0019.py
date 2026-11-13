"""Reward 0019.
"""
from __future__ import annotations

REWARD = "reward_0019"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (19 % 30), "gold": 10 + (19 % 20)}
