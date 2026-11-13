"""Puzzle 0079.
"""
from __future__ import annotations

PUZZLE = "puzzle_0079"

def check(answer: str) -> dict:
    expected = f"key_{79}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{79}"
