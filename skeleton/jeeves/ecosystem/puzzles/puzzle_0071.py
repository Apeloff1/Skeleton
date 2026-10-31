"""Puzzle 0071.
"""
from __future__ import annotations

PUZZLE = "puzzle_0071"

def check(answer: str) -> dict:
    expected = f"key_{71}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{71}"
