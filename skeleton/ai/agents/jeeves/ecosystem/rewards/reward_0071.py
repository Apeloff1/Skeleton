"""Reward 0071.
"""
from __future__ import annotations

REWARD = "reward_0071"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (71 % 30), "gold": 10 + (71 % 20)}
