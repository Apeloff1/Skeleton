"""Puzzle 0077.
"""
from __future__ import annotations

PUZZLE = "puzzle_0077"

def check(answer: str) -> dict:
    expected = f"key_{77}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{77}"
