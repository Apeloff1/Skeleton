"""Puzzle 0076.
"""
from __future__ import annotations

PUZZLE = "puzzle_0076"

def check(answer: str) -> dict:
    expected = f"key_{76}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{76}"
