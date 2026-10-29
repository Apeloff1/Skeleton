"""Reward 0062.
"""
from __future__ import annotations

REWARD = "reward_0062"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (62 % 30), "gold": 10 + (62 % 20)}
