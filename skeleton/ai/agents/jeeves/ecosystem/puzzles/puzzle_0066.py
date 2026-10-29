"""Puzzle 0066.
"""
from __future__ import annotations

PUZZLE = "puzzle_0066"

def check(answer: str) -> dict:
    expected = f"key_{66}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{66}"
