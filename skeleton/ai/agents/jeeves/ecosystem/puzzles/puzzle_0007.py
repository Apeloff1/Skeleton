"""Puzzle 0007.
"""
from __future__ import annotations

PUZZLE = "puzzle_0007"

def check(answer: str) -> dict:
    expected = f"key_{7}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{7}"
