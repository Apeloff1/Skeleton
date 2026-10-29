"""Puzzle 0019.
"""
from __future__ import annotations

PUZZLE = "puzzle_0019"

def check(answer: str) -> dict:
    expected = f"key_{19}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{19}"
