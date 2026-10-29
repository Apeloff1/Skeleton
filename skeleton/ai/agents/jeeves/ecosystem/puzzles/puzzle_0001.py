"""Puzzle 0001.
"""
from __future__ import annotations

PUZZLE = "puzzle_0001"

def check(answer: str) -> dict:
    expected = f"key_{1}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{1}"
