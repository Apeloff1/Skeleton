"""Reward 0055.
"""
from __future__ import annotations

REWARD = "reward_0055"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (55 % 30), "gold": 10 + (55 % 20)}
