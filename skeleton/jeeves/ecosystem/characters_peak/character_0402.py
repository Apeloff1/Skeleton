"""Character peak 0402.
"""
from __future__ import annotations

ID = "character_peak_0402"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 402, "tier": 402 % 5}

def apply(context: str = "") -> dict:
    if not context and 402 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
