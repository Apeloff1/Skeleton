"""Puzzle 0052.
"""
from __future__ import annotations

PUZZLE = "puzzle_0052"

def check(answer: str) -> dict:
    expected = f"key_{52}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{52}"
