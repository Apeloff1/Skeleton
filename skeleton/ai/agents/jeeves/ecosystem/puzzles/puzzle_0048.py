"""Puzzle 0048.
"""
from __future__ import annotations

PUZZLE = "puzzle_0048"

def check(answer: str) -> dict:
    expected = f"key_{48}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{48}"
