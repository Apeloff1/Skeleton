"""Puzzle 0038.
"""
from __future__ import annotations

PUZZLE = "puzzle_0038"

def check(answer: str) -> dict:
    expected = f"key_{38}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{38}"
