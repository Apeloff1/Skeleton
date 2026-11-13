"""Reward 0117.
"""
from __future__ import annotations

REWARD = "reward_0117"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (117 % 30), "gold": 10 + (117 % 20)}
