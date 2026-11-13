"""Reward 0033.
"""
from __future__ import annotations

REWARD = "reward_0033"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (33 % 30), "gold": 10 + (33 % 20)}
