"""Weather scale 0100.
"""
from __future__ import annotations

ID = "weather_scale_0100"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 100, "tier": 100 % 5}

def apply(context: str = "") -> dict:
    if not context and 100 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
