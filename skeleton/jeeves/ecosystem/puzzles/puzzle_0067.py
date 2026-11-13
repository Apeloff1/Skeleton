"""Puzzle 0067.
"""
from __future__ import annotations

PUZZLE = "puzzle_0067"

def check(answer: str) -> dict:
    expected = f"key_{67}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{67}"
