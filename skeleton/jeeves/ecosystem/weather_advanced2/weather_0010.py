"""Weather advanced 0010.
"""
from __future__ import annotations

ID = "weather_adv_0010"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 10, "tier": 10 % 5}

def apply(context: str = "") -> dict:
    if not context and 10 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
