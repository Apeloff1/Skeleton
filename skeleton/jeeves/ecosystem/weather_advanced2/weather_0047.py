"""Weather advanced 0047.
"""
from __future__ import annotations

ID = "weather_adv_0047"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 47, "tier": 47 % 5}

def apply(context: str = "") -> dict:
    if not context and 47 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
