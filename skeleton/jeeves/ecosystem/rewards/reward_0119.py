"""Reward 0119.
"""
from __future__ import annotations

REWARD = "reward_0119"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (119 % 30), "gold": 10 + (119 % 20)}
