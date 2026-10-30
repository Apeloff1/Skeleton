"""Weather scale 0095.
"""
from __future__ import annotations

ID = "weather_scale_0095"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 95, "tier": 95 % 5}

def apply(context: str = "") -> dict:
    if not context and 95 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
