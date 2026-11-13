"""Puzzle 0042.
"""
from __future__ import annotations

PUZZLE = "puzzle_0042"

def check(answer: str) -> dict:
    expected = f"key_{42}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{42}"
