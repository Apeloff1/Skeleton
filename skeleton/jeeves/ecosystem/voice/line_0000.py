"""Voice line 0000.
"""
from __future__ import annotations

LINE = "voice_0000"

def play(speaker: str) -> dict:
    if not speaker:
        return {"ok": False, "reason": "no_speaker"}
    return {"ok": True, "line": LINE, "speaker": speaker, "duration": 1.2}
