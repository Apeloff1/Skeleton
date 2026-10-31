"""Event 0004.
"""
from __future__ import annotations

EVENT = "event_0004"

def active(now: float, start: float, end: float) -> dict:
    return {"ok": True, "event": EVENT, "active": start <= now <= end}
