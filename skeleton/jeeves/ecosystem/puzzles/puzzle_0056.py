"""Puzzle 0056.
"""
from __future__ import annotations

PUZZLE = "puzzle_0056"

def check(answer: str) -> dict:
    expected = f"key_{56}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{56}"
