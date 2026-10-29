"""Puzzle 0021.
"""
from __future__ import annotations

PUZZLE = "puzzle_0021"

def check(answer: str) -> dict:
    expected = f"key_{21}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{21}"
