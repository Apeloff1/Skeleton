"""Weather scale 0074.
"""
from __future__ import annotations

ID = "weather_scale_0074"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 74, "tier": 74 % 5}

def apply(context: str = "") -> dict:
    if not context and 74 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
