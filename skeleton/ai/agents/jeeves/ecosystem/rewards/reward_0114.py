"""Reward 0114.
"""
from __future__ import annotations

REWARD = "reward_0114"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (114 % 30), "gold": 10 + (114 % 20)}
