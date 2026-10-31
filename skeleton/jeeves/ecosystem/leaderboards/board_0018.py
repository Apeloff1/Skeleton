"""Leaderboard 0018.
"""
from __future__ import annotations

BOARD = "board_0018"

def submit(player: str, score: int) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "board": BOARD, "player": player, "score": score}
