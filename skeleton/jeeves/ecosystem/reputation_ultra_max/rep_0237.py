"""Rep ultra_max 0237.
"""
from __future__ import annotations

ID = "rep_ultra_max_0237"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 237}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
