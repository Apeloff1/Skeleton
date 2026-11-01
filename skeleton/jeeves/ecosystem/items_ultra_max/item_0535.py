"""Item ultra_max 0535.
"""
from __future__ import annotations

ID = "item_ultra_max_0535"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 535, "tier": 535 % 5}

def apply(context: str = "") -> dict:
    if not context and 535 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
