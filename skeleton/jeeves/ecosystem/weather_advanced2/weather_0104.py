"""Weather advanced 0104.
"""
from __future__ import annotations

ID = "weather_adv_0104"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 104, "tier": 104 % 5}

def apply(context: str = "") -> dict:
    if not context and 104 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
