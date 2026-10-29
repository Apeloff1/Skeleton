"""Reward 0111.
"""
from __future__ import annotations

REWARD = "reward_0111"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (111 % 30), "gold": 10 + (111 % 20)}
