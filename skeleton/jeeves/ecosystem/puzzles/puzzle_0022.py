"""Puzzle 0022.
"""
from __future__ import annotations

PUZZLE = "puzzle_0022"

def check(answer: str) -> dict:
    expected = f"key_{22}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{22}"
