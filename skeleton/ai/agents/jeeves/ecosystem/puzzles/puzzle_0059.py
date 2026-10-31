"""Puzzle 0059.
"""
from __future__ import annotations

PUZZLE = "puzzle_0059"

def check(answer: str) -> dict:
    expected = f"key_{59}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{59}"
