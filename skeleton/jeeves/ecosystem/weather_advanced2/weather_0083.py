"""Weather advanced 0083.
"""
from __future__ import annotations

ID = "weather_adv_0083"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 83, "tier": 83 % 5}

def apply(context: str = "") -> dict:
    if not context and 83 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
