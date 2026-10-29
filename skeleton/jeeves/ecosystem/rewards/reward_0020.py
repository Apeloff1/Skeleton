"""Reward 0020.
"""
from __future__ import annotations

REWARD = "reward_0020"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (20 % 30), "gold": 10 + (20 % 20)}
