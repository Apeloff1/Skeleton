"""Puzzle 0011.
"""
from __future__ import annotations

PUZZLE = "puzzle_0011"

def check(answer: str) -> dict:
    expected = f"key_{11}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{11}"
