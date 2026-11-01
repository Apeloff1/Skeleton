"""Rep ultra_max 0239.
"""
from __future__ import annotations

ID = "rep_ultra_max_0239"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 239}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
