"""Puzzle 0041.
"""
from __future__ import annotations

PUZZLE = "puzzle_0041"

def check(answer: str) -> dict:
    expected = f"key_{41}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{41}"
