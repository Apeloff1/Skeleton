"""Event 0031.
"""
from __future__ import annotations

EVENT = "event_0031"

def active(now: float, start: float, end: float) -> dict:
    return {"ok": True, "event": EVENT, "active": start <= now <= end}
