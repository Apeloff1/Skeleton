"""Puzzle 0003.
"""
from __future__ import annotations

PUZZLE = "puzzle_0003"

def check(answer: str) -> dict:
    expected = f"key_{3}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{3}"
