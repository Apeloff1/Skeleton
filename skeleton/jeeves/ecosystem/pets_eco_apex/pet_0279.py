"""Pet eco_apex 0279.
"""
from __future__ import annotations

ID = "pet_eco_apex_0279"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 279}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
