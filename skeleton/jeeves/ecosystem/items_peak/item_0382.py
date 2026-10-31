"""Item peak 0382.
"""
from __future__ import annotations

ID = "item_peak_0382"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 382, "tier": 382 % 5}

def apply(context: str = "") -> dict:
    if not context and 382 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
