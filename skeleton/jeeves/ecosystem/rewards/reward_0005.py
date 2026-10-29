"""Reward 0005.
"""
from __future__ import annotations

REWARD = "reward_0005"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (5 % 30), "gold": 10 + (5 % 20)}
