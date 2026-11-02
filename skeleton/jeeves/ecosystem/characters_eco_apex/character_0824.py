"""Character eco_apex 0824.
"""
from __future__ import annotations

ID = "character_eco_apex_0824"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 824, "tier": 824 % 5}

def apply(context: str = "") -> dict:
    if not context and 824 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
