"""Reward 0038.
"""
from __future__ import annotations

REWARD = "reward_0038"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (38 % 30), "gold": 10 + (38 % 20)}
