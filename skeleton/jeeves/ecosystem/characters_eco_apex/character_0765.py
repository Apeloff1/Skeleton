"""Character eco_apex 0765.
"""
from __future__ import annotations

ID = "character_eco_apex_0765"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 765, "tier": 765 % 5}

def apply(context: str = "") -> dict:
    if not context and 765 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
