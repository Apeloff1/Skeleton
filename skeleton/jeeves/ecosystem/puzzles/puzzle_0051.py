"""Puzzle 0051.
"""
from __future__ import annotations

PUZZLE = "puzzle_0051"

def check(answer: str) -> dict:
    expected = f"key_{51}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{51}"
