"""Puzzle 0030.
"""
from __future__ import annotations

PUZZLE = "puzzle_0030"

def check(answer: str) -> dict:
    expected = f"key_{30}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{30}"
