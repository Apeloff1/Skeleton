"""Puzzle 0072.
"""
from __future__ import annotations

PUZZLE = "puzzle_0072"

def check(answer: str) -> dict:
    expected = f"key_{72}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{72}"
