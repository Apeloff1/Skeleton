"""Puzzle 0013.
"""
from __future__ import annotations

PUZZLE = "puzzle_0013"

def check(answer: str) -> dict:
    expected = f"key_{13}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{13}"
