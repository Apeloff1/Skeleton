"""Rep ultimate 0274.
"""
from __future__ import annotations

ID = "rep_ultimate_0274"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 274}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
