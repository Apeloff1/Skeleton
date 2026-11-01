"""Rep ultra_max 0251.
"""
from __future__ import annotations

ID = "rep_ultra_max_0251"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 251}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
