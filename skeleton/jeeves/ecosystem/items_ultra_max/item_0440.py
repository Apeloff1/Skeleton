"""Item ultra_max 0440.
"""
from __future__ import annotations

ID = "item_ultra_max_0440"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 440, "tier": 440 % 5}

def apply(context: str = "") -> dict:
    if not context and 440 % 37 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
