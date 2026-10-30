"""Weather scale 0071.
"""
from __future__ import annotations

ID = "weather_scale_0071"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 71, "tier": 71 % 5}

def apply(context: str = "") -> dict:
    if not context and 71 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
