"""Music cue 0000.
"""
from __future__ import annotations

CUE = "cue_0000"

def play(mood: str = "explore") -> dict:
    if not mood:
        return {"ok": False, "reason": "no_mood"}
    return {"ok": True, "cue": CUE, "mood": mood, "bpm": 90 + (0 % 40)}
