"""Character eco_apex 0873.
"""
from __future__ import annotations

ID = "character_eco_apex_0873"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 873, "tier": 873 % 5}

def apply(context: str = "") -> dict:
    if not context and 873 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
