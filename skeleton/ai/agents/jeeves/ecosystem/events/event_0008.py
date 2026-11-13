"""Event 0008.
"""
from __future__ import annotations

EVENT = "event_0008"

def active(now: float, start: float, end: float) -> dict:
    return {"ok": True, "event": EVENT, "active": start <= now <= end}
