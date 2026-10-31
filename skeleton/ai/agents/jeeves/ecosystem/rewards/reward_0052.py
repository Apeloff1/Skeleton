"""Reward 0052.
"""
from __future__ import annotations

REWARD = "reward_0052"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (52 % 30), "gold": 10 + (52 % 20)}
