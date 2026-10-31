"""Animation clip 0059.
"""
from __future__ import annotations

CLIP = "clip_0059"

def duration() -> float:
    return round(0.4 + (59 % 8) * 0.15, 2)

def play(speed: float = 1.0) -> dict:
    return {"ok": True, "clip": CLIP, "duration": duration(), "speed": max(0.1, speed)}
