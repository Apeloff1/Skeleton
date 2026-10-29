"""Puzzle 0044.
"""
from __future__ import annotations

PUZZLE = "puzzle_0044"

def check(answer: str) -> dict:
    expected = f"key_{44}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{44}"
