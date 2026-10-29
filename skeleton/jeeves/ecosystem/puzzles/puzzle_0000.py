"""Puzzle 0000.
"""
from __future__ import annotations

PUZZLE = "puzzle_0000"

def check(answer: str) -> dict:
    expected = f"key_{0}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{0}"
