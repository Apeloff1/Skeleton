"""Item eco_apex 0976.
"""
from __future__ import annotations

ID = "item_eco_apex_0976"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 976, "tier": 976 % 5}

def apply(context: str = "") -> dict:
    if not context and 976 % 53 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
