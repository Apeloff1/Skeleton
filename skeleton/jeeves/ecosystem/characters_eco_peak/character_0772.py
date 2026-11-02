"""Character eco_peak 0772.
"""
from __future__ import annotations

ID = "character_eco_peak_0772"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 772, "tier": 772 % 5}

def apply(context: str = "") -> dict:
    if not context and 772 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
