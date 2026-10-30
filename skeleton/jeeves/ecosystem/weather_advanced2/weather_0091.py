"""Weather advanced 0091.
"""
from __future__ import annotations

ID = "weather_adv_0091"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 91, "tier": 91 % 5}

def apply(context: str = "") -> dict:
    if not context and 91 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
