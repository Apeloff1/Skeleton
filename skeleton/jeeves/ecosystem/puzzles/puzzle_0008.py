"""Puzzle 0008.
"""
from __future__ import annotations

PUZZLE = "puzzle_0008"

def check(answer: str) -> dict:
    expected = f"key_{8}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{8}"
