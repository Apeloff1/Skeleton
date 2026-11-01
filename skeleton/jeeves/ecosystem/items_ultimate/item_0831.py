"""Item ultimate 0831.
"""
from __future__ import annotations

ID = "item_ultimate_0831"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 831, "tier": 831 % 5}

def apply(context: str = "") -> dict:
    if not context and 831 % 43 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
