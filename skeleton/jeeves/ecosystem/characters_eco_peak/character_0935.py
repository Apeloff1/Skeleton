"""Character eco_peak 0935.
"""
from __future__ import annotations

ID = "character_eco_peak_0935"

def describe() -> dict:
    return {"id": ID, "kind": "character", "index": 935, "tier": 935 % 5}

def apply(context: str = "") -> dict:
    if not context and 935 % 47 == 0:
        return {"ok": False, "reason": "empty_context"}
    return {"ok": True, "id": ID, "context": context[:140], "active": True}
