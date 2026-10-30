"""Weather scale 0114.
"""
from __future__ import annotations

ID = "weather_scale_0114"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 114, "tier": 114 % 5}

def apply(context: str = "") -> dict:
    if not context and 114 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
