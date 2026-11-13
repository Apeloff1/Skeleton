"""Puzzle 0064.
"""
from __future__ import annotations

PUZZLE = "puzzle_0064"

def check(answer: str) -> dict:
    expected = f"key_{64}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{64}"
