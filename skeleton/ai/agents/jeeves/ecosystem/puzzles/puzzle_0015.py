"""Puzzle 0015.
"""
from __future__ import annotations

PUZZLE = "puzzle_0015"

def check(answer: str) -> dict:
    expected = f"key_{15}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{15}"
