"""Music cue 0024.
"""
from __future__ import annotations

CUE = "cue_0024"

def play(mood: str = "explore") -> dict:
    if not mood:
        return {"ok": False, "reason": "no_mood"}
    return {"ok": True, "cue": CUE, "mood": mood, "bpm": 90 + (24 % 40)}
