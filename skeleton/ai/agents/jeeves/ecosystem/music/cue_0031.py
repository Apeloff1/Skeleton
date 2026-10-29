"""Music cue 0031.
"""
from __future__ import annotations

CUE = "cue_0031"

def play(mood: str = "explore") -> dict:
    if not mood:
        return {"ok": False, "reason": "no_mood"}
    return {"ok": True, "cue": CUE, "mood": mood, "bpm": 90 + (31 % 40)}
