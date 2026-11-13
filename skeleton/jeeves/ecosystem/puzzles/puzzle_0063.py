"""Puzzle 0063.
"""
from __future__ import annotations

PUZZLE = "puzzle_0063"

def check(answer: str) -> dict:
    expected = f"key_{63}"
    return {"ok": answer == expected, "puzzle": PUZZLE, "solved": answer == expected}

def hint() -> str:
    return f"Look for key_{63}"
