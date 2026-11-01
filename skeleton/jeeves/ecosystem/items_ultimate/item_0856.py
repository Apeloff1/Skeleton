"""Item ultimate 0856.
"""
from __future__ import annotations

ID = "item_ultimate_0856"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 856, "tier": 856 % 5}

def apply(context: str = "") -> dict:
    if not context and 856 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
