"""Character eco_apex 0680.
"""
from __future__ import annotations

ID = "character_eco_apex_0680"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 680, "tier": 680 % 5}

def apply(context: str = "") -> dict:
    if not context and 680 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
