"""Item ultimate 0871.
"""
from __future__ import annotations

ID = "item_ultimate_0871"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 871, "tier": 871 % 5}

def apply(context: str = "") -> dict:
    if not context and 871 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
