"""Puzzle 0017.
"""
from __future__ import annotations

PUZZLE = "puzzle_0017"

def check(answer: str) -> dict:
    expected = f"key_{17}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{17}"
