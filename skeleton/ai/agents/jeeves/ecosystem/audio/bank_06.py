"""Audio bank 06.
"""
from __future__ import annotations

BANK = "bank_06"

def cue(event: str) -> dict:
    if not event:
        return {"ok": False, "reason": "empty_event"}
    return {"ok": True, "bank": BANK, "event": event, "gain": round(0.5 + (6 % 5) * 0.05, 2)}
