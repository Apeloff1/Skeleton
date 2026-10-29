"""Reward 0047.
"""
from __future__ import annotations

REWARD = "reward_0047"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (47 % 30), "gold": 10 + (47 % 20)}
