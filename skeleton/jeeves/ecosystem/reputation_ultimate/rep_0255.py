"""Rep ultimate 0255.
"""
from __future__ import annotations

ID = "rep_ultimate_0255"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 255}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
