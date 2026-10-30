"""Weather scale 0093.
"""
from __future__ import annotations

ID = "weather_scale_0093"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 93, "tier": 93 % 5}

def apply(context: str = "") -> dict:
    if not context and 93 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
