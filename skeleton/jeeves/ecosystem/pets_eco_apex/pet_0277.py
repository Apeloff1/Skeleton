"""Pet eco_apex 0277.
"""
from __future__ import annotations

ID = "pet_eco_apex_0277"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 277}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
