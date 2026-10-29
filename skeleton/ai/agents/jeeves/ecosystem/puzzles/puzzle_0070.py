"""Puzzle 0070.
"""
from __future__ import annotations

PUZZLE = "puzzle_0070"

def check(answer: str) -> dict:
    expected = f"key_{70}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{70}"
