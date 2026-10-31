"""Reward 0105.
"""
from __future__ import annotations

REWARD = "reward_0105"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (105 % 30), "gold": 10 + (105 % 20)}
