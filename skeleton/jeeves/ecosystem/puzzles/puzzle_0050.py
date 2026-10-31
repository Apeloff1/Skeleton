"""Puzzle 0050.
"""
from __future__ import annotations

PUZZLE = "puzzle_0050"

def check(answer: str) -> dict:
    expected = f"key_{50}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{50}"
