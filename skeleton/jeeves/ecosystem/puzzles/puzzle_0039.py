"""Puzzle 0039.
"""
from __future__ import annotations

PUZZLE = "puzzle_0039"

def check(answer: str) -> dict:
    expected = f"key_{39}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{39}"
