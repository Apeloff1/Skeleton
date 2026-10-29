"""Puzzle 0032.
"""
from __future__ import annotations

PUZZLE = "puzzle_0032"

def check(answer: str) -> dict:
    expected = f"key_{32}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{32}"
