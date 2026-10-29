"""Reward 0096.
"""
from __future__ import annotations

REWARD = "reward_0096"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (96 % 30), "gold": 10 + (96 % 20)}
