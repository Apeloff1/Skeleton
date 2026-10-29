"""Animation clip 0055.
"""
from __future__ import annotations

CLIP = "clip_0055"

def duration() -> float:
    return round(0.4 + (55 % 8) * 0.15, 2)

def play(speed: float = 1.0) -> dict:
    return {"ok": True, "clip": CLIP, "duration": duration(), "speed": max(0.1, speed)}
