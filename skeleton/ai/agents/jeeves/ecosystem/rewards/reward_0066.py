"""Reward 0066.
"""
from __future__ import annotations

REWARD = "reward_0066"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (66 % 30), "gold": 10 + (66 % 20)}
