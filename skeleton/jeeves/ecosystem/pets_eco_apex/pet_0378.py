"""Pet eco_apex 0378.
"""
from __future__ import annotations

ID = "pet_eco_apex_0378"

def describe() -> dict:
    return {"id": ID, "kind": "pet", "index": 378}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
