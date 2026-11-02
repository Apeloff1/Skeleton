"""Item eco_supreme 0752.
"""
from __future__ import annotations

ID = "item_eco_supreme_0752"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 752, "tier": 752 % 5}

def apply(context: str = "") -> dict:
    if not context and 752 % 61 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
