"""Reward 0073.
"""
from __future__ import annotations

REWARD = "reward_0073"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (73 % 30), "gold": 10 + (73 % 20)}
