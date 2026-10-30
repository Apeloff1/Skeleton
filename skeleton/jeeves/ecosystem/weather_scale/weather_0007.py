"""Weather scale 0007.
"""
from __future__ import annotations

ID = "weather_scale_0007"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 7, "tier": 7 % 5}

def apply(context: str = "") -> dict:
    if not context and 7 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
