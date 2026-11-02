"""Item eco_supreme 0916.
"""
from __future__ import annotations

ID = "item_eco_supreme_0916"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 916, "tier": 916 % 5}

def apply(context: str = "") -> dict:
    if not context and 916 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
