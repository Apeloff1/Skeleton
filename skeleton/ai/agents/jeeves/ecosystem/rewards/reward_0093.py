"""Reward 0093.
"""
from __future__ import annotations

REWARD = "reward_0093"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (93 % 30), "gold": 10 + (93 % 20)}
