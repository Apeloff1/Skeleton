"""Puzzle 0020.
"""
from __future__ import annotations

PUZZLE = "puzzle_0020"

def check(answer: str) -> dict:
    expected = f"key_{20}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{20}"
