"""Music cue 0001.
"""
from __future__ import annotations

CUE = "cue_0001"

def play(mood: str = "explore") -> dict:
    if not mood:
        return {"ok": False, "reason": "no_mood"}
    return {"ok": True, "cue": CUE, "mood": mood, "bpm": 90 + (1 % 40)}
