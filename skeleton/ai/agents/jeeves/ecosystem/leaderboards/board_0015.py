"""Leaderboard 0015.
"""
from __future__ import annotations

BOARD = "board_0015"

def submit(player: str, score: int) -> dict:
    if not player:
        return {"ok": False, "reason": "no_player"}
    return {"ok": True, "board": BOARD, "player": player, "score": score}
