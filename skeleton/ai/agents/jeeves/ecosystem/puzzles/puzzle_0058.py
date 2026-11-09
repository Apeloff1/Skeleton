"""Puzzle 0058.
"""
from __future__ import annotations

PUZZLE = "puzzle_0058"

def check(answer: str) -> dict:
    expected = f"key_{58}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{58}"
