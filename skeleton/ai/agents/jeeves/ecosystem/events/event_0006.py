"""Event 0006.
"""
from __future__ import annotations

EVENT = "event_0006"

def active(now: float, start: float, end: float) -> dict:
    return {"ok": True, "event": EVENT, "active": start <= now <= end}
