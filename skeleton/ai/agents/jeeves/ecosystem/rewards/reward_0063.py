"""Reward 0063.
"""
from __future__ import annotations

REWARD = "reward_0063"

def grant(player: str) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "reward": REWARD, "player": player, "xp": 50 + (63 % 30), "gold": 10 + (63 % 20)}
