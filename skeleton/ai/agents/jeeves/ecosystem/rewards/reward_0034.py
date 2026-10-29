"""Reward 0034.
"""
from __future__ import annotations

REWARD = "reward_0034"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (34 % 30), "gold": 10 + (34 % 20)}
