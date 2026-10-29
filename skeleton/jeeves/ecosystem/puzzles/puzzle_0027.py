"""Puzzle 0027.
"""
from __future__ import annotations

PUZZLE = "puzzle_0027"

def check(answer: str) -> dict:
    expected = f"key_{27}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{27}"
