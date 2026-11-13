"""Reward 0037.
"""
from __future__ import annotations

REWARD = "reward_0037"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (37 % 30), "gold": 10 + (37 % 20)}
