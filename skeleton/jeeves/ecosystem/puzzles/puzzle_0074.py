"""Puzzle 0074.
"""
from __future__ import annotations

PUZZLE = "puzzle_0074"

def check(answer: str) -> dict:
    expected = f"key_{74}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{74}"
