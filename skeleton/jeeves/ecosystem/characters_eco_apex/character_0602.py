"""Character eco_apex 0602.
"""
from __future__ import annotations

ID = "character_eco_apex_0602"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 602, "tier": 602 % 5}

def apply(context: str = "") -> dict:
    if not context and 602 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
