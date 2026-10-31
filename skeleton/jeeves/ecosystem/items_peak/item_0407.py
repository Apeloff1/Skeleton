"""Item peak 0407.
"""
from __future__ import annotations

ID = "item_peak_0407"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 407, "tier": 407 % 5}

def apply(context: str = "") -> dict:
    if not context and 407 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
