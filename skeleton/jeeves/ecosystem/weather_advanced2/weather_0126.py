"""Weather advanced 0126.
"""
from __future__ import annotations

ID = "weather_adv_0126"

def describe() -> dict:
    return {"id": ID, "kind": "weather", "index": 126, "tier": 126 % 5}

def apply(context: str = "") -> dict:
    if not context and 126 % 13 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
