"""Reward 0021.
"""
from __future__ import annotations

REWARD = "reward_0021"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (21 % 30), "gold": 10 + (21 % 20)}
