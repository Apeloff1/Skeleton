"""Puzzle 0035.
"""
from __future__ import annotations

PUZZLE = "puzzle_0035"

def check(answer: str) -> dict:
    expected = f"key_{35}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{35}"
