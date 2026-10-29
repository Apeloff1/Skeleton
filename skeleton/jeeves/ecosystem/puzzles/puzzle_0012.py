"""Puzzle 0012.
"""
from __future__ import annotations

PUZZLE = "puzzle_0012"

def check(answer: str) -> dict:
    expected = f"key_{12}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{12}"
