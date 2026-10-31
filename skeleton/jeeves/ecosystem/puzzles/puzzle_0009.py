"""Puzzle 0009.
"""
from __future__ import annotations

PUZZLE = "puzzle_0009"

def check(answer: str) -> dict:
    expected = f"key_{9}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{9}"
