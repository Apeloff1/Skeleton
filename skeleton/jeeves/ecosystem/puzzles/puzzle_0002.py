"""Puzzle 0002.
"""
from __future__ import annotations

PUZZLE = "puzzle_0002"

def check(answer: str) -> dict:
    expected = f"key_{2}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{2}"
