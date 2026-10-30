"""Weather scale 0004.
"""
from __future__ import annotations

ID = "weather_scale_0004"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 4, "tier": 4 % 5}

def apply(context: str = "") -> dict:
    if not context and 4 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
