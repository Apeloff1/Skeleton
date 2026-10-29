"""Reward 0113.
"""
from __future__ import annotations

REWARD = "reward_0113"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (113 % 30), "gold": 10 + (113 % 20)}
