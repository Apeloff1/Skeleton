"""Music cue 0037.
"""
from __future__ import annotations

CUE = "cue_0037"

def play(mood: str = "explore") -> dict:
    if not mood:
        return {"ok": False, "reason": "no_mood"}
    return {"ok": True, "cue": CUE, "mood": mood, "bpm": 90 + (37 % 40)}
