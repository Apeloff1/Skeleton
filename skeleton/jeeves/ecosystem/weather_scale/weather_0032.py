"""Weather scale 0032.
"""
from __future__ import annotations

ID = "weather_scale_0032"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 32, "tier": 32 % 5}

def apply(context: str = "") -> dict:
    if not context and 32 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
