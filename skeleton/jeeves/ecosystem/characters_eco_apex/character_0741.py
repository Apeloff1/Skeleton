"""Character eco_apex 0741.
"""
from __future__ import annotations

ID = "character_eco_apex_0741"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 741, "tier": 741 % 5}

def apply(context: str = "") -> dict:
    if not context and 741 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
