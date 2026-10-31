"""Puzzle 0078.
"""
from __future__ import annotations

PUZZLE = "puzzle_0078"

def check(answer: str) -> dict:
    expected = f"key_{78}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{78}"
