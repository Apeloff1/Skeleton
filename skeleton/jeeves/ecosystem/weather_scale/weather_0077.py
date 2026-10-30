"""Weather scale 0077.
"""
from __future__ import annotations

ID = "weather_scale_0077"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 77, "tier": 77 % 5}

def apply(context: str = "") -> dict:
    if not context and 77 % 11 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
