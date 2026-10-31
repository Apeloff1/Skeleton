"""Puzzle 0047.
"""
from __future__ import annotations

PUZZLE = "puzzle_0047"

def check(answer: str) -> dict:
    expected = f"key_{47}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{47}"
