"""Puzzle 0068.
"""
from __future__ import annotations

PUZZLE = "puzzle_0068"

def check(answer: str) -> dict:
    expected = f"key_{68}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{68}"
