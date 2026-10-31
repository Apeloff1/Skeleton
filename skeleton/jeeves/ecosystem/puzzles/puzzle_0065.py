"""Puzzle 0065.
"""
from __future__ import annotations

PUZZLE = "puzzle_0065"

def check(answer: str) -> dict:
    expected = f"key_{65}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{65}"
