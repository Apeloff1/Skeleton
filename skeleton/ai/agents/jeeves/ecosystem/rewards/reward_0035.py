"""Reward 0035.
"""
from __future__ import annotations

REWARD = "reward_0035"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (35 % 30), "gold": 10 + (35 % 20)}
