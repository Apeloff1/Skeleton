"""Music cue 0038.
"""
from __future__ import annotations

CUE = "cue_0038"

def play(mood: str = "explore") -> dict:
    if not mood:
        return {"ok": False, "reason": "no_mood"}
    return {"ok": True, "cue": CUE, "mood": mood, "bpm": 90 + (38 % 40)}
