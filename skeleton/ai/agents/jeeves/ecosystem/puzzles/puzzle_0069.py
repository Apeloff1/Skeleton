"""Puzzle 0069.
"""
from __future__ import annotations

PUZZLE = "puzzle_0069"

def check(answer: str) -> dict:
    expected = f"key_{69}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{69}"
