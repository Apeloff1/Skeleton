"""Reward 0042.
"""
from __future__ import annotations

REWARD = "reward_0042"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (42 % 30), "gold": 10 + (42 % 20)}
