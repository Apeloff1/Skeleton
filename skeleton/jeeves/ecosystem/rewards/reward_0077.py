"""Reward 0077.
"""
from __future__ import annotations

REWARD = "reward_0077"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (77 % 30), "gold": 10 + (77 % 20)}
