"""Puzzle 0018.
"""
from __future__ import annotations

PUZZLE = "puzzle_0018"

def check(answer: str) -> dict:
    expected = f"key_{18}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{18}"
