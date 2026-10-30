"""Weather advanced 0072.
"""
from __future__ import annotations

ID = "weather_adv_0072"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 72, "tier": 72 % 5}

def apply(context: str = "") -> dict:
    if not context and 72 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
