"""Reward 0068.
"""
from __future__ import annotations

REWARD = "reward_0068"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (68 % 30), "gold": 10 + (68 % 20)}
