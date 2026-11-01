"""Rep supreme 0273.
"""
from __future__ import annotations

ID = "rep_supreme_0273"

def describe() -> dict:
    return {"id": ID, "kind": "rep", "index": 273}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
