"""Reward 0098.
"""
from __future__ import annotations

REWARD = "reward_0098"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (98 % 30), "gold": 10 + (98 % 20)}
