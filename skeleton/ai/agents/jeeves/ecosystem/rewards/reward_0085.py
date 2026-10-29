"""Reward 0085.
"""
from __future__ import annotations

REWARD = "reward_0085"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (85 % 30), "gold": 10 + (85 % 20)}
