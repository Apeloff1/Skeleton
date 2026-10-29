"""Music cue 0035.
"""
from __future__ import annotations

CUE = "cue_0035"

def play(mood: str = "explore") -> dict:
    if not mood:
        return {"ok": False, "reason": "no_mood"}
    return {"ok": True, "cue": CUE, "mood": mood, "bpm": 90 + (35 % 40)}
