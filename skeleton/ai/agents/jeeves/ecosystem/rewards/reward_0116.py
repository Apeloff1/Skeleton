"""Reward 0116.
"""
from __future__ import annotations

REWARD = "reward_0116"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (116 % 30), "gold": 10 + (116 % 20)}
