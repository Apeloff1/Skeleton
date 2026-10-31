"""Puzzle 0014.
"""
from __future__ import annotations

PUZZLE = "puzzle_0014"

def check(answer: str) -> dict:
    expected = f"key_{14}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{14}"
