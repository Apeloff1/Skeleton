"""Puzzle 0023.
"""
from __future__ import annotations

PUZZLE = "puzzle_0023"

def check(answer: str) -> dict:
    expected = f"key_{23}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{23}"
