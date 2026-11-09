"""Ending 013.
"""
from __future__ import annotations

ENDING = "ending_013"

def sequence(optical: float = 0.9) -> list[str]:
    phases = ["intro", "climax", "resolve"]
    if optical > 0.93:
        phases.append("epilogue")
    return phases

def title() -> str:
    return f"Ending {ENDING}"
