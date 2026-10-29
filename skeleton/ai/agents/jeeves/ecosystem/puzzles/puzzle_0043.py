"""Puzzle 0043.
"""
from __future__ import annotations

PUZZLE = "puzzle_0043"

def check(answer: str) -> dict:
    expected = f"key_{43}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{43}"
