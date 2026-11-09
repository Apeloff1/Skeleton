"""Reward 0050.
"""
from __future__ import annotations

REWARD = "reward_0050"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (50 % 30), "gold": 10 + (50 % 20)}
