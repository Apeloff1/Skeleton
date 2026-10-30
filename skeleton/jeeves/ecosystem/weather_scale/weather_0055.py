"""Weather scale 0055.
"""
from __future__ import annotations

ID = "weather_scale_0055"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 55, "tier": 55 % 5}

def apply(context: str = "") -> dict:
    if not context and 55 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
