"""Puzzle 0033.
"""
from __future__ import annotations

PUZZLE = "puzzle_0033"

def check(answer: str) -> dict:
    expected = f"key_{33}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{33}"
