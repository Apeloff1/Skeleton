"""Voice line 0040.
"""
from __future__ import annotations

LINE = "voice_0040"

def play(speaker: str) -> dict:
    if not speaker:
        return {"ok": False, "reason": "no_speaker"}
    return {"ok": True, "line": LINE, "speaker": speaker, "duration": 1.2}
