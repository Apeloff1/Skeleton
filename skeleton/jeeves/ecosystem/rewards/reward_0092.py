"""Reward 0092.
"""
from __future__ import annotations

REWARD = "reward_0092"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (92 % 30), "gold": 10 + (92 % 20)}
