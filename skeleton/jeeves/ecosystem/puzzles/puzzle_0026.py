"""Puzzle 0026.
"""
from __future__ import annotations

PUZZLE = "puzzle_0026"

def check(answer: str) -> dict:
    expected = f"key_{26}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{26}"
