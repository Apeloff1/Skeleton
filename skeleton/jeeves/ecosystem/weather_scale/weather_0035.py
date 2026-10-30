"""Weather scale 0035.
"""
from __future__ import annotations

ID = "weather_scale_0035"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 35, "tier": 35 % 5}

def apply(context: str = "") -> dict:
    if not context and 35 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
