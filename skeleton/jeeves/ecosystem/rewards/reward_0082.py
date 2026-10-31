"""Reward 0082.
"""
from __future__ import annotations

REWARD = "reward_0082"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (82 % 30), "gold": 10 + (82 % 20)}
