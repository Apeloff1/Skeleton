"""Puzzle 0062.
"""
from __future__ import annotations

PUZZLE = "puzzle_0062"

def check(answer: str) -> dict:
    expected = f"key_{62}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{62}"
