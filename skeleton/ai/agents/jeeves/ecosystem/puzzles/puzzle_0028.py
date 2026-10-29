"""Puzzle 0028.
"""
from __future__ import annotations

PUZZLE = "puzzle_0028"

def check(answer: str) -> dict:
    expected = f"key_{28}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{28}"
