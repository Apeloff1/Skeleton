"""Puzzle 0010.
"""
from __future__ import annotations

PUZZLE = "puzzle_0010"

def check(answer: str) -> dict:
    expected = f"key_{10}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{10}"
