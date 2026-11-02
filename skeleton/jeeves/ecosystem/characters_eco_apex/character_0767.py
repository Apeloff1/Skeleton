"""Character eco_apex 0767.
"""
from __future__ import annotations

ID = "character_eco_apex_0767"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 767, "tier": 767 % 5}

def apply(context: str = "") -> dict:
    if not context and 767 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
