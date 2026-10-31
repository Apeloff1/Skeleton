"""Event 0022.
"""
from __future__ import annotations

EVENT = "event_0022"

def active(now: float, start: float, end: float) -> dict:
    return {"ok": True, "event": EVENT, "active": start <= now <= end}
