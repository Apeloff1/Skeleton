"""Event 0003.
"""
from __future__ import annotations

EVENT = "event_0003"

def active(now: float, start: float, end: float) -> dict:
    return {"ok": True, "event": EVENT, "active": start <= now <= end}
