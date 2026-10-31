"""Reward 0088.
"""
from __future__ import annotations

REWARD = "reward_0088"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (88 % 30), "gold": 10 + (88 % 20)}
