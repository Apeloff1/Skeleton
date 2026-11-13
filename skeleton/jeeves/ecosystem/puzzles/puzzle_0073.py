"""Puzzle 0073.
"""
from __future__ import annotations

PUZZLE = "puzzle_0073"

def check(answer: str) -> dict:
    expected = f"key_{73}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{73}"
