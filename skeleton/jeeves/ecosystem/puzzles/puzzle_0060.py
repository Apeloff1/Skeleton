"""Puzzle 0060.
"""
from __future__ import annotations

PUZZLE = "puzzle_0060"

def check(answer: str) -> dict:
    expected = f"key_{60}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{60}"
