"""Reward 0029.
"""
from __future__ import annotations

REWARD = "reward_0029"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (29 % 30), "gold": 10 + (29 % 20)}
