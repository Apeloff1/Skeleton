"""Weather advanced 0149.
"""
from __future__ import annotations

ID = "weather_adv_0149"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 149, "tier": 149 % 5}

def apply(context: str = "") -> dict:
    if not context and 149 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
