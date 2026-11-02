"""Rep eco_apex 0270.
"""
from __future__ import annotations

ID = "rep_eco_apex_0270"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 270}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
