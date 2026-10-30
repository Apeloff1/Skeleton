"""Weather scale 0078.
"""
from __future__ import annotations

ID = "weather_scale_0078"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 78, "tier": 78 % 5}

def apply(context: str = "") -> dict:
    if not context and 78 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
