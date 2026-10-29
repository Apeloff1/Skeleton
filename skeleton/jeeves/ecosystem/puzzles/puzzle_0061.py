"""Puzzle 0061.
"""
from __future__ import annotations

PUZZLE = "puzzle_0061"

def check(answer: str) -> dict:
    expected = f"key_{61}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{61}"
