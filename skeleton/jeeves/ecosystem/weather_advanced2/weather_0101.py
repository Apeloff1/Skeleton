"""Weather advanced 0101.
"""
from __future__ import annotations

ID = "weather_adv_0101"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 101, "tier": 101 % 5}

def apply(context: str = "") -> dict:
    if not context and 101 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
