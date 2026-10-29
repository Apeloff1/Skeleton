"""Puzzle 0034.
"""
from __future__ import annotations

PUZZLE = "puzzle_0034"

def check(answer: str) -> dict:
    expected = f"key_{34}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{34}"
