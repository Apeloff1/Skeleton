"""Puzzle 0075.
"""
from __future__ import annotations

PUZZLE = "puzzle_0075"

def check(answer: str) -> dict:
    expected = f"key_{75}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{75}"
