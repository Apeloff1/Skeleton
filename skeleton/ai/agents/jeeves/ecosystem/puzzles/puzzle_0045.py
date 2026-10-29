"""Puzzle 0045.
"""
from __future__ import annotations

PUZZLE = "puzzle_0045"

def check(answer: str) -> dict:
    expected = f"key_{45}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{45}"
