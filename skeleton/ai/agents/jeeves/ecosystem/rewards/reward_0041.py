"""Reward 0041.
"""
from __future__ import annotations

REWARD = "reward_0041"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (41 % 30), "gold": 10 + (41 % 20)}
