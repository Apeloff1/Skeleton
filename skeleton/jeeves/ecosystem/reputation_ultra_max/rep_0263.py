"""Rep ultra_max 0263.
"""
from __future__ import annotations

ID = "rep_ultra_max_0263"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 263}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
