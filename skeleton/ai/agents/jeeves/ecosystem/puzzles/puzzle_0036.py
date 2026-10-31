"""Puzzle 0036.
"""
from __future__ import annotations

PUZZLE = "puzzle_0036"

def check(answer: str) -> dict:
    expected = f"key_{36}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{36}"
