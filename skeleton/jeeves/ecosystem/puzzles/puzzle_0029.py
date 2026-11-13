"""Puzzle 0029.
"""
from __future__ import annotations

PUZZLE = "puzzle_0029"

def check(answer: str) -> dict:
    expected = f"key_{29}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{29}"
