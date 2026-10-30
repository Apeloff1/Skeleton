"""Weather advanced 0017.
"""
from __future__ import annotations

ID = "weather_adv_0017"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 17, "tier": 17 % 5}

def apply(context: str = "") -> dict:
    if not context and 17 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
