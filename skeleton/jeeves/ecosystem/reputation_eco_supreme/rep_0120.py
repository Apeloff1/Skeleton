"""Rep eco_supreme 0120.
"""
from __future__ import annotations

ID = "rep_eco_supreme_0120"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 120}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
