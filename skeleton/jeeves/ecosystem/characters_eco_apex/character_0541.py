"""Character eco_apex 0541.
"""
from __future__ import annotations

ID = "character_eco_apex_0541"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 541, "tier": 541 % 5}

def apply(context: str = "") -> dict:
    if not context and 541 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
