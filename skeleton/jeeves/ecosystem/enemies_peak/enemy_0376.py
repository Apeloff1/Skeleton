"""Enemy peak 0376.
"""
from __future__ import annotations

ID = "enemy_peak_0376"

def describe() -> dict:
    return {"id": ID, "kind": "enemy", "index": 376, "tier": 376 % 5}

def apply(context: str = "") -> dict:
    if not context and 376 % 23 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
